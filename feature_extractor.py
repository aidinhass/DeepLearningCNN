# feature_extractor.py.py
# Created by abdularis on 02/07/18

import matplotlib.pyplot as plt
import numpy as np
import scipy.misc
import glob
import sqlite3
import pickle
import database
import importlib
import tensorflow as tf
import modelarch.cnnarch1_3
import data_config as cfg
import os
import tqdm
from tsnn.operations import Dropout
from data_reader import DirDataSet


one_hot_labels = np.array(cfg.one_hot_labels)


class Image(object):
    def __init__(self, path, truth, pred_labels, features):
        self.path = path
        self.truth = truth
        self.pred_labels = pred_labels
        self.features = features


def create_database(path):
    conn = sqlite3.connect(path, detect_types=sqlite3.PARSE_DECLTYPES)
    if not os.path.exists(path):
        conn.execute("CREATE TABLE images_repo ("
                     "id integer primary key autoincrement,"
                     "path text,"
                     "truth text,"
                     "pred_labels text,"
                     "feature array)")
        conn.commit()
    return conn


def insert_feature(db, record):
    db.executemany("INSERT INTO images_repo ('path', 'truth', 'pred_labels', 'feature') VALUES (?, ?, ?, ?)", record)
    db.commit()


def get_preds_labels(preds_probs):
    return [one_hot_labels[indices[:2]] for indices in np.flip(np.argsort(preds_probs), axis=1)]


def extract_features(test_dir_split, model_arch_module, model_path):

    db = create_database('images.db')
    model = model_arch_module.build_model_arch()
    extractor = model.stored_ops['features']
    data_test = DirDataSet(32, test_dir_split, cfg.one_hot)

    saver = tf.train.Saver()
    with tf.Session() as sess:
        saver.restore(sess, model_path)

        for step in range(data_test.batch_count):
            images, one_hot = data_test.next_batch()
            images = images / 255.0
            truth_indexes = np.argmax(one_hot, 1)

            truth_labels = [one_hot_labels[i] for i in truth_indexes]
            file_paths = data_test.current_batch_file_paths

            preds_probs, features = model.predict(sess, images, extra_fetches=[extractor])
            preds_labels = [','.join(labels) for labels in get_preds_labels(preds_probs)]

            data_records = [(file_paths[i], truth_labels[i], preds_labels[i], features[i]) for i in range(len(file_paths))]

            insert_feature(db, data_records)


def query_images(db, query_labels):
    db_images = db.execute(
        'select path, truth, pred_labels, feature from images_repo where pred_labels like "%{}%" or pred_labels like "%{}%"'.format(query_labels[0],
                                                                                                    query_labels[1]))
    return [Image(row[0], row[1], row[2], row[3]) for row in db_images]


def query_items_count(db, truth):
    return db.execute('select count(*) from images_repo where truth = "{}"'.format(truth)).fetchone()[0]


def cd(a, b):
    return 1 - (np.dot(a, b) / (np.sqrt((a**2).sum()) * np.sqrt((b**2).sum())))


def show(query_img, images):
    for i in range(45):
        s = plt.subplot(9, 5, i + 1)
        s.set_axis_off()
        plt.imshow(images[i])
    plt.imshow(query_img)
    plt.title("query image")
    plt.show()


def save_obj(obj, name):
    with open('obj_' + name + ".pkl", 'wr') as f:
        pickle.dump(obj, f)


def count_relevant_items(truth, images):
    count = 0
    for img, _ in images:
        if img.truth == truth:
            count = count + 1
    return count


def calculate_precision_recall(test_dir_split, model_arch_module, model_path):

    db = create_database('images.db')
    model = model_arch_module.build_model_arch()
    extractor = model.stored_ops['features']
    data_test = DirDataSet(32, test_dir_split, cfg.one_hot)

    per_class_precisions = {key: [] for key in cfg.one_hot_labels}
    per_class_recalls = {key: [] for key in cfg.one_hot_labels}

    saver = tf.train.Saver()
    with tf.Session() as sess:
        saver.restore(sess, model_path)

        for _ in tqdm.tqdm(range(data_test.batch_count)):
            images, one_hot = data_test.next_batch()
            images = images / 255.0
            truth_indexes = np.argmax(one_hot, 1)

            truth_labels = [one_hot_labels[i] for i in truth_indexes]

            preds_probs, features = model.predict(sess, images, extra_fetches=[extractor])
            preds_labels = get_preds_labels(preds_probs)

            for i in range(len(truth_labels)):
                curr_features = features[i]
                curr_truth = truth_labels[i]
                db_images = query_images(db, preds_labels[i])

                db_images = [(img, cd(curr_features, img.features)) for img in db_images]
                db_images = sorted(db_images, key=lambda d: d[1])

                filtered_results = [img for img in filter(lambda d: d[1] < 0.5, db_images)]

                relevant_items_count = count_relevant_items(curr_truth, filtered_results)

                precision = relevant_items_count / len(filtered_results)
                recall = relevant_items_count / query_items_count(db, curr_truth)

                per_class_precisions[curr_truth].append(precision)
                per_class_recalls[curr_truth].append(recall)

                # print('truth ', curr_truth, ' lbls ', preds_labels[i], ' len ', len(db_images), " filtered ", len(filtered_results))
                # filtered_results_images = [scipy.misc.imread(img[0].path) for img in filtered_results]
                #
                # show(images[i], filtered_results_images)

        save_obj(per_class_precisions, 'per_class_precisions')
        save_obj(per_class_recalls, 'per_class_recalls')


# calculate_precision_recall('compute-engine/split/test', importlib.import_module('modelarch.cnnarch1_3'), 'compute-engine/model-1_3/cnnarch1_3-197')
#
#
# model = modelarch.cnnarch1_3.build_model_arch()
# sess = tf.Session()
# saver = tf.train.Saver()
# saver.restore(sess, 'compute-engine/model-1_3/cnnarch1_3-197')
#
# extractor = model.stored_ops['features']
#
# query_img = scipy.misc.imread('compute-engine/split/test/backpack/6.jpg') / 255.
#
# query_pred, query_features = model.predict(sess, [query_img], extra_fetches=[extractor])
#
# query_pred = query_pred[0]
# query_features = query_features[0]
#
# ordered_pred_idx = np.argsort(query_pred)
# query_labels = [cfg.one_hot_labels[ordered_pred_idx[-1]], cfg.one_hot_labels[ordered_pred_idx[-2]]]
#
# db = sqlite3.connect('images.db', detect_types=sqlite3.PARSE_DECLTYPES)
#
# db_images = db.execute('select * from images_repo where pred_labels like "%{}%" or pred_labels like "%{}%"'.format(query_labels[0], query_labels[1]))
# db_images = [row for row in db_images]


#
#
# def euc(a, b):
#     return np.linalg.norm(a-b)
#
#
# def imread(path):
#     return np.array(scipy.misc.imread(path, mode='RGB'))
#
#
# import random
# img_paths = glob.glob('compute-engine/split/test/microwave/*.jpg')[:25]
# img_paths.extend(glob.glob('compute-engine/split/test/teapot/*.jpg')[:25])
#
# # img_paths = glob.glob('compute-engine/split/test/*/*.jpg')
# random.shuffle(img_paths)
#
# imgs = np.array([imread(p) for p in img_paths[:50]]) / 255.
#
# model = modelarch.cnnarch1_3.build_model_arch()
# sess = tf.Session()
# saver = tf.train.Saver()
# saver.restore(sess, 'compute-engine/model-1_3/cnnarch1_3-186')
#
# extractor = model.stored_ops['features']
#
# imgs_features = sess.run(extractor, feed_dict={Dropout.keep_prob: 1.0, model.x: imgs})
#
# # query_img = imread(img_paths[0]) / 255.
# query_img = imread('my-mug.jpg') / 255.
# query_features = sess.run(extractor, feed_dict={Dropout.keep_prob: 1.0, model.x: [query_img]})[0]
#
# img_distances = [cd(query_features, f) for f in imgs_features]
#
# imgs_order = sorted(list(zip(img_distances, imgs)), key=lambda t: t[0])
#
#
# def show():
#     for i in range(len(imgs_order[:45])):
#         s = plt.subplot(9, 5, i + 1)
#         s.set_axis_off()
#         plt.imshow(imgs_order[i][1])
#