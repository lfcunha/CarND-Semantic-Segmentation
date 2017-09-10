import tensorflow as tf
from tensorflow.python.platform import gfile
from tensorflow.core.protobuf import saved_model_pb2
from tensorflow.python.util import compat

with tf.Session() as sess:
    model_filename ='model/model.pb'
    with gfile.FastGFile(model_filename, 'rb') as f:
        data = compat.as_bytes(f.read())
        sm = saved_model_pb2.SavedModel()
        sm.ParseFromString(data)
        g_in = tf.import_graph_def(sm.meta_graphs[0].graph_def)

LOGDIR='.'
train_writer = tf.summary.FileWriter(LOGDIR)
train_writer.add_graph(sess.graph)
