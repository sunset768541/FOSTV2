import time
import os
import random
import numpy as np
import tensorflow as tf
import cv2
from itertools import compress
from data_provider.data_utils import check_and_validate_polys, crop_area, rotate_image, generate_rbox, get_project_matrix_and_width, sparse_tuple_from, crop_area_fix
from data_provider.ICDAR_loader import ICDARLoader
from data_provider.CTW_loader import CTW_loader
# from data_provider.SynthText_loader import SynthTextLoader
from data_provider.data_enqueuer import GeneratorEnqueuer

"""
tf.app.flags.DEFINE_string('training_data_dir_ic13', '', 'training dataset to use')
tf.app.flags.DEFINE_string('training_data_dir_ic17', '', 'ic17 training data dir')
tf.app.flags.DEFINE_string('training_data_dir_ic15', '', 'ic15 training data dir')
tf.app.flags.DEFINE_string('training_gt_dir_ic13', '', 'ic13 training dataset ground-truth to use')
tf.app.flags.DEFINE_string('training_gt_dir_ic17', '', 'ic15 training dataset ground-truth to use')
tf.app.flags.DEFINE_string('training_gt_dir_ic15', '', 'ic17 training dataset ground-truth to use')
"""

tf.app.flags.DEFINE_string('training_data_dir', default='E:\Learn\AI\DL\DataSets\ch4_training_images', help='training images dir')
tf.app.flags.DEFINE_string('training_gt_data_dir', default='E:\Learn\AI\DL\DataSets\ch4_training_localization_transcription_gt', help='training gt dir')

FLAGS = tf.app.flags.FLAGS

def generator(input_size=512, batch_size=12, random_scale=np.array([0.8, 0.85, 0.9, 0.95, 1.0, 1.1, 1.2]),):
    # data_loader = SynthTextLoader()
    # data_loader = ICDARLoader(edition='13', shuffle=True)
    data_loader = CTW_loader(shuffle=True)
    image_list = np.array(data_loader.get_images(FLAGS.training_data_dir))
    # print("所有数据："+str(image_list.size))
    image_list_pick = []
    for imfn in image_list:
            image_list_pick.append(imfn.split("'\\'")[-1])
    image_list = np.array(image_list_pick)
    print('{} training images in {} '.format(image_list.shape[0], FLAGS.training_data_dir))
    index = np.arange(0, image_list.shape[0])
    # print("我index=")
    # print(index)
    while True:
        np.random.shuffle(index)
        batch_images = []
        batch_image_fns = []
        batch_score_maps = []
        batch_geo_maps = []
        batch_training_masks = []

        batch_text_polyses = []
        batch_text_tagses = []
        batch_boxes_masks = []

        batch_text_labels = []
        count = 0
        # print(index)
        for i in index:
            try:
                # print('我G-1:')
                # print(i)
                im_fn = image_list[i]
                # print(im_fn)
                # if im_fn.split(".")[0][-1] == '0' or im_fn.split(".")[0][-1] == '2':
                #     continue
                im = cv2.imread(os.path.join(FLAGS.training_data_dir, im_fn))
                h, w, _ = im.shape
                file_name = "gt_" + (im_fn.split('\\')[-1]).replace('jpg', 'txt')
                # file_name = im_fn.replace(im_fn.split('.')[1], 'txt') # using for synthtext
                txt_fn = os.path.join(FLAGS.training_gt_data_dir, file_name)
                if not os.path.exists(txt_fn):
                    print('text file {} does not exists'.format(txt_fn))
                    continue
                text_polys, text_tags, text_labels = data_loader.load_annotation(txt_fn) # Change for load text transiption
                # print(file_name)
                if text_polys.shape[0] == 0:
                    print(file_name+" text_polys.shape[0]是0")
                    continue

                text_polys, text_tags, text_labels = check_and_validate_polys(text_polys, text_tags, text_labels, (h, w))

                ############################# Data Augmentation ##############################
                """
                # random scale this image
                rd_scale = np.random.choice(random_scale)
                im = cv2.resize(im, dsize=None, fx=rd_scale, fy=rd_scale)
                text_polys *= rd_scale

                # rotate image from [-10, 10]
                angle = random.randint(-10, 10)
                im, text_polys = rotate_image(im, text_polys, angle)

                # 600×600 random samples are cropped.
                # im, text_polys, text_tags, text_label = crop_area(im, text_polys, text_tags, text_label, crop_background=False)
                # im, text_polys, text_tags, selected_poly = crop_area(im, text_polys, text_tags, crop_background=False)
                im, text_polys, text_tags, selected_poly = crop_area_fix(im, text_polys, text_tags, crop_size=(600, 600))
                # text_labels = [text_labels[i] for i in selected_poly]
                """
                if text_polys.shape[0] == 0 or len(text_labels) == 0:
                    print(file_name +" text_polys text_labels 是 0")
                    continue

                # pad the image to the training input size or the longer side of image
                new_h, new_w, _ = im.shape
                max_h_w_i = np.max([new_h, new_w, input_size])
                im_padded = np.zeros((max_h_w_i, max_h_w_i, 3), dtype=np.uint8)
                im_padded[:new_h, :new_w, :] = im.copy()
                im = im_padded
                # resize the image to input size
                new_h, new_w, _ = im.shape
                resize_h = input_size
                resize_w = input_size
                im = cv2.resize(im, dsize=(resize_w, resize_h))
                resize_ratio_3_x = resize_w/float(new_w)
                resize_ratio_3_y = resize_h/float(new_h)
                text_polys[:, :, 0] *= resize_ratio_3_x
                text_polys[:, :, 1] *= resize_ratio_3_y
                new_h, new_w, _ = im.shape
                # print(text_polys)
                score_map, geo_map, training_mask, rectangles = generate_rbox((new_h, new_w), text_polys, text_tags)

                mask = [not (word == [-1]) for word in text_labels]
                text_labels = list(compress(text_labels, mask))
                rectangles = list(compress(rectangles, mask))
                # print('我G1:'+file_name)
                assert len(text_labels) == len(rectangles), "rotate rectangles' num is not equal to text label"

                if len(text_labels) == 0:
                    print(file_name + "label 是0")
                    continue

                boxes_mask = np.array([count] * len(rectangles))

                count += 1

                batch_images.append(im[:, :, ::-1].astype(np.float32))
                batch_image_fns.append(im_fn)
                batch_score_maps.append(score_map[::4, ::4, np.newaxis].astype(np.float32))
                batch_geo_maps.append(geo_map[::4, ::4, :].astype(np.float32))
                batch_training_masks.append(training_mask[::4, ::4, np.newaxis].astype(np.float32))

                batch_text_polyses.append(rectangles)
                batch_boxes_masks.append(boxes_mask)
                batch_text_labels.extend(text_labels)
                batch_text_tagses.append(text_tags)
                # print('我G2:'+file_name)
                if len(batch_images) == batch_size:
                    # print('我G3-1')
                    batch_text_polyses = np.concatenate(batch_text_polyses)
                    batch_text_tagses = np.concatenate(batch_text_tagses)
                    batch_transform_matrixes, batch_box_widths = get_project_matrix_and_width(batch_text_polyses, batch_text_tagses)
                    # print('我G3-2')
                    # TODO limit the batch size of recognition
                    batch_text_labels_sparse = sparse_tuple_from(np.array(batch_text_labels))
                    # print('我G3-3')

                    # yield images, image_fns, score_maps, geo_maps, training_masks
                    yield batch_images, batch_image_fns, batch_score_maps, batch_geo_maps, batch_training_masks, batch_transform_matrixes, batch_boxes_masks, batch_box_widths, batch_text_labels_sparse, batch_text_polyses, batch_text_labels
                    # print('我G3-4')
                    batch_images = []
                    batch_image_fns = []
                    batch_score_maps = []
                    batch_geo_maps = []
                    batch_training_masks = []
                    batch_text_polyses = []
                    batch_text_tagses = []
                    batch_boxes_masks = []
                    batch_text_labels = []
                    count = 0
                    # print('我G3')
                # print('我G4')
            except Exception as e:
                print('异常了c '+str(e))
                # import traceback
                print(im_fn)
                # traceback.print_exc(e)
                continue
        break


def get_batch(num_workers, **kwargs):
    try:
        enqueuer = GeneratorEnqueuer(generator(**kwargs), use_multiprocessing=False)
        enqueuer.start(max_queue_size=1, workers=1)
        # enqueuer = GeneratorEnqueuer(generator(**kwargs), use_multiprocessing=True)
        print('Generator use 10 batches for buffering, this may take a while, you can tune this yourself.')
        # enqueuer.start(max_queue_size=10, workers=num_workers)
        generator_output = None
        while True:
            print("开始取数据")
            while not enqueuer.queue.empty():
                if not enqueuer.queue.empty():
                    print("我来取数据了a "+str(enqueuer.queue.qsize()))
                    generator_output = enqueuer.queue.get()
                    print("我来取数据了b "+str(enqueuer.queue.qsize()))
                    break
                else:
                    time.sleep(0.1)
            yield generator_output
            generator_output = None
    finally:
        print('Generator use 10 batches完成了')
        if enqueuer is not None:
            enqueuer.stop()


def test():
    font = cv2.FONT_HERSHEY_SIMPLEX
    dg = get_batch(num_workers=1, input_size=512, batch_size=4)
    for iter in range(2000):
        print("iter: ", iter)
        data = next(dg)
        imgs = data[0]
        imgs_name = data[1]
        polygons = data[-2]
        labels = data[-1]
        masks = data[6]
        prev_start_index = 0
        for i, (img, mask, img_name) in enumerate(zip(imgs, masks, imgs_name)):
            # img_name = ''
            im = img.copy()
            poly_start_index = len(masks[i-1])
            poly_end_index = len(masks[i-1]) + len(mask)
            for poly, la,  in zip(polygons[prev_start_index:(prev_start_index+len(mask))], labels[prev_start_index:prev_start_index+len(mask)]):
                cv2.polylines(img, [poly.astype(np.int32).reshape((-1, 1, 2))], True, color=(255, 255, 0), thickness=1)
                # trans = ground_truth_to_word(la)
                # img_name = img_name + trans + '_'
            img_name = img_name[:-1] + '.jpg'
            cv2.imwrite("./polygons/" + os.path.basename(img_name), img)

            prev_start_index += len(mask)

if __name__ == '__main__':
    test()
