import os.path
import tensorflow as tf
import helper
import warnings
from distutils.version import LooseVersion
import project_tests as tests


data_prefix = '/home/a/SDC/Term3/CarND-Semantic-Segmentation/data/data_road/'
training_data_prefix = data_prefix + 'training/'
testing_data_prefix = data_prefix + 'testing/'
vgg_path = '/home/a/SDC/Term3/CarND-Semantic-Segmentation/weights'
trained_models_path = '/home/a/SDC/Term3/CarND-Semantic-Segmentation/trained_model'
trained_models_filename = (trained_models_path +
                           'weights.{epoch:03d}-{val_loss:.3f}.hdf5')

# Check TensorFlow Version
assert LooseVersion(tf.__version__) >= LooseVersion(
    '1.0'), 'Please use TensorFlow version 1.0 or newer.  You are using {}'.format(tf.__version__)
print('TensorFlow Version: {}'.format(tf.__version__))

# Check for a GPU
if not tf.test.gpu_device_name():
    warnings.warn('No GPU found. Please use a GPU to train your neural network.')
else:
    print('Default GPU Device: {}'.format(tf.test.gpu_device_name()))


def load_vgg(sess, vgg_path):
    """
    Load Pretrained VGG Model into TensorFlow.
    :param sess: TensorFlow Session
    :param vgg_path: Path to vgg folder, containing "variables/" and "saved_model.pb"
    :return: Tuple of Tensors from VGG model (image_input, keep_prob, layer3_out, layer4_out, layer7_out)
    """

    vgg_tag = 'vgg16'

    vgg_input_tensor_name = 'image_input:0'
    vgg_keep_prob_tensor_name = 'keep_prob:0'
    vgg_layer3_out_tensor_name = 'layer3_out:0'
    vgg_layer4_out_tensor_name = 'layer4_out:0'
    vgg_layer7_out_tensor_name = 'layer7_out:0'

    tf.saved_model.loader.load(sess, [vgg_tag], vgg_path)
    graph = tf.get_default_graph()

    image_input = graph.get_tensor_by_name(vgg_input_tensor_name)
    keep_prob = graph.get_tensor_by_name(vgg_keep_prob_tensor_name)
    layer3_out = graph.get_tensor_by_name(vgg_layer3_out_tensor_name)
    layer4_out = graph.get_tensor_by_name(vgg_layer4_out_tensor_name)
    layer7_out = graph.get_tensor_by_name(vgg_layer7_out_tensor_name)

    return image_input, keep_prob, layer3_out, layer4_out, layer7_out


def layers(vgg_layer3_out, vgg_layer4_out, vgg_layer7_out, num_classes):
    """
    Create the layers for a fully convolutional network.
    Build skip-layers using the vgg layers.
    :param vgg_layer7_out: TF Tensor for VGG Layer 3 output
    :param vgg_layer4_out: TF Tensor for VGG Layer 4 output
    :param vgg_layer3_out: TF Tensor for VGG Layer 7 output
    :param num_classes: Number of classes to classify
    :return: The Tensor for the last layer of output
    """

    # deconvolution and upsample of the layers 3, 4, 7
    layer7_encoded_conv1_1 = tf.layers.conv2d(vgg_layer7_out, num_classes, 1, strides=(1,1),padding='same',
                                   kernel_regularizer=tf.contrib.layers.l2_regularizer(1e-3),
                                   kernel_initializer=tf.truncated_normal_initializer(stddev=0.01))
    layer7_decoded_upsample = tf.layers.conv2d_transpose(layer7_encoded_conv1_1, num_classes, 4, 2, 'SAME',
                                                kernel_regularizer=tf.contrib.layers.l2_regularizer(1e-3),
                                             kernel_initializer=tf.truncated_normal_initializer(stddev=0.01))

    layer4_encoded_conv_1x1 = tf.layers.conv2d(vgg_layer4_out, num_classes, 1, strides=(1,1), padding='same',
                                   kernel_regularizer=tf.contrib.layers.l2_regularizer(1e-3),
                                   kernel_initializer=tf.truncated_normal_initializer(stddev=0.01))
    layer4_skipped_add_layer7 = tf.add(layer7_decoded_upsample, layer4_encoded_conv_1x1)
    layer4_decoded_upsample = tf.layers.conv2d_transpose(layer4_skipped_add_layer7, num_classes, 8, 2, 'SAME',
                                                         kernel_regularizer=tf.contrib.layers.l2_regularizer(1e-3),
                                                         kernel_initializer=tf.truncated_normal_initializer(stddev=0.01)
                                                         )

    layer3_encoded_conv_1x1 = tf.layers.conv2d(vgg_layer3_out, num_classes, 1, strides=(1,1), padding='same',
                                   kernel_regularizer=tf.contrib.layers.l2_regularizer(1e-3),
                                   kernel_initializer=tf.truncated_normal_initializer(stddev=0.01))
    layer3_skipped_Add_layer4 = tf.add(layer4_decoded_upsample, layer3_encoded_conv_1x1)

    # upscale to the originl size
    layer3_decoded_upsample = tf.layers.conv2d_transpose(layer3_skipped_Add_layer4, num_classes, 16, strides=(8,8), padding='same',
                                             kernel_regularizer=tf.contrib.layers.l2_regularizer(1e-3),
                                             kernel_initializer=tf.truncated_normal_initializer(stddev=0.01))

    return layer3_decoded_upsample


def optimize(nn_last_layer, correct_label, learning_rate, num_classes):
    """
    Build the TensorFLow loss and optimizer operations.
    :param nn_last_layer: TF Tensor of the last layer in the neural network
    :param correct_label: TF Placeholder for the correct label image
    :param learning_rate: TF Placeholder for the learning rate
    :param num_classes: Number of classes to classify
    :return: Tuple of (logits, train_op, cross_entropy_loss)
    """

    logits = tf.reshape(nn_last_layer, (-1, num_classes))
    labels = tf.reshape(correct_label, (-1, num_classes))
    cross_entropy_loss = tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits(logits=logits, labels=labels))
    optimizer = tf.train.AdamOptimizer(learning_rate)
    train_op = optimizer.minimize(cross_entropy_loss)
    return logits, train_op, cross_entropy_loss


def train_nn(sess, epochs, batch_size, get_batches_fn, train_op, cross_entropy_loss,
             input_image, correct_label, keep_prob, learning_rate):
    """
    Train neural network and print out the loss during training.
    :param sess: TF Session
    :param epochs: Number of epochs
    :param batch_size: Batch size
    :param get_batches_fn: Function to get batches of training data.  Call using get_batches_fn(batch_size)
    :param train_op: TF Operation to train the neural network
    :param cross_entropy_loss: TF Tensor for the amount of loss
    :param input_image: TF Placeholder for input images
    :param correct_label: TF Placeholder for label images
    :param keep_prob: TF Placeholder for dropout keep probability
    :param learning_rate: TF Placeholder for learning rate
    """

    # Create a summary writer, add the 'graph' to the event file.
    log_dir = './logs'
    train_writer = tf.summary.FileWriter(log_dir + '/train', sess.graph)
    test_writer = tf.summary.FileWriter(log_dir + '/test')

    sess.run(tf.global_variables_initializer())
    sess.run(tf.local_variables_initializer())

    print("Starting...")

    for epoch in range(epochs):
        for iteration, (images, labels) in enumerate(get_batches_fn(batch_size)):
            if images.shape[0] != batch_size:
                continue
            feed_dict = {input_image: images,
                         correct_label: labels,
                         keep_prob: 0.3,
                         learning_rate: 1e-3}
            _, loss = sess.run([train_op, cross_entropy_loss],
                               feed_dict=feed_dict)
            print("Epoch {}; Batch: {}, Loss {:.5f}".format(epoch, iteration, loss))
            # pass


tests.test_load_vgg(load_vgg, tf)
tests.test_layers(layers)
tests.test_optimize(optimize)
tests.test_train_nn(train_nn)


def run():
    global g_iou
    global g_iou_op
    num_classes = 2
    image_shape = (160, 576)
    data_dir = './data'
    runs_dir = './runs'
    tests.test_for_kitti_dataset(data_dir)
    num_epochs = 3
    batch_size = 10

    # Download pretrained vgg model
    helper.maybe_download_pretrained_vgg(data_dir)

    # OPTIONAL: Train and Inference on the cityscapes dataset instead of the Kitti dataset.
    # You'll need a GPU with at least 10 teraFLOPS to train on.
    #  https://www.cityscapes-dataset.com/

    with tf.Session() as sess:
        # Path to vgg model
        vgg_path = os.path.join(data_dir, 'vgg')
        # Create function to get batches
        get_batches_fn = helper.gen_batch_function(os.path.join(data_dir, 'data_road/training'), image_shape)

        # OPTIONAL: Augment Images for better results
        #  https://datascience.stackexchange.com/questions/5224/how-to-prepare-augment-images-for-neural-network

        # Build NN using load_vgg, layers, and optimize function
        input_image, keep_prob, vgg_layer3_out, vgg_layer4_out, vgg_layer7_out = load_vgg(sess, vgg_path)
        output_layer = layers(vgg_layer3_out, vgg_layer4_out, vgg_layer7_out, num_classes)

        correct_label = tf.placeholder(tf.float32, shape=[batch_size, image_shape[0], image_shape[1], 2])
        learning_rate = tf.placeholder(tf.float32, shape=[])
        logits, train_op, cross_entropy_loss = optimize(output_layer, correct_label, learning_rate, num_classes)
        g_iou, g_iou_op = tf.metrics.mean_iou(tf.argmax(tf.reshape(correct_label, (-1, 2)), -1), tf.argmax(logits, -1),
                                              num_classes)
        saver = tf.train.Saver()

        # load pre-trained model from disk
        checkpoint = tf.train.get_checkpoint_state('./model')
        if checkpoint and checkpoint.model_checkpoint_path:
            saver.restore(sess, checkpoint.model_checkpoint_path)

        # Train NN using the train_nn function
        train_nn(sess, num_epochs, batch_size, get_batches_fn, train_op, cross_entropy_loss,
                 input_image, correct_label, keep_prob, learning_rate)

        save_path = saver.save(sess, "./model/model.ckpt")
        print("Saved Model to: {}".format(save_path))
        saver.export_meta_graph("./model/model.meta")
        tf.train.write_graph(sess.graph_def, "./model/", "model.pb", False)

        # Save inference data using helper.save_inference_samples
        helper.save_inference_samples(runs_dir, data_dir, sess, image_shape, logits, keep_prob, input_image)

        # OPTIONAL: Apply the trained model to a video


if __name__ == '__main__':
    run()
