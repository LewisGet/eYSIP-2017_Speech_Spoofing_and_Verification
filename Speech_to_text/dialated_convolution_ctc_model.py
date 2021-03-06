import tensorflow as tf
import numpy as np
import utils
import time
import os
from utils import sparse_tuple_from as sparse_tuple_from
from utils import pad_sequences as pad_sequences

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'


#defining all the constants and hyperparameters
num_features = 13
num_o1 = 128
num_o2 = 128
num_o3 = 28
filter_size = 1
num_blocks = 3
initial_learning_rate = 0.0003
momentum = 0.9

num_epochs = 65000
batch_size = 150
num_examples = 44085
num_batches_per_epoch = int(num_examples / batch_size)

#loading the input matrix created by the python script 'creatingdataset.py'
train_inputs = np.load('train_input.npy')
train_targets = np.load('train_label.npy')

#THE MAIN CODE STARTS HERE
#We start building the model(graph) of our neural netowrk
graph = tf.Graph()
with graph.as_default():
    # e.g: log filter bank or MFCC features
    # Has size [batch_size, max_stepsize, num_features], but the
    # batch_size and max_stepsize can vary along each step
    inputs = tf.placeholder(tf.float32, [None, None, num_features], name='inputs')

    # Here we use sparse_placeholder that will generate a
    # SparseTensor required by ctc_loss op.
    targets = tf.sparse_placeholder(tf.int32, name='targets')

    # 1d array of size [batch_size]
    seq_len = tf.placeholder(tf.int32, [None], name='seq_len')

    #the shapes are defined for using it in convolution
    shape = tf.Variable(tf.truncated_normal([filter_size, num_features, num_o1], stddev=0.05))
    shape2 = tf.Variable(tf.truncated_normal([7, num_o1, num_o2], stddev=0.05))
    shape3 = tf.Variable(tf.truncated_normal([7, num_o2, num_o3], stddev=0.05))

    #1st convolution layer
    l1 = tf.nn.conv1d(inputs, shape, 1, padding='SAME')

    #function for residual block
    def res_block(tensor, rate):
        l2 = tf.nn.convolution(tensor, shape2, padding='SAME', dilation_rate=[rate])
        l2 = tf.tanh(l2)

        l3 = tf.nn.convolution(l1, shape2, padding='SAME', dilation_rate=[rate])
        l3 = tf.sigmoid(l3)

        l4 = l2 * l3

        l4 = tf.nn.conv1d(l4, shape2, 1, padding='SAME')

        return l4 + tensor, l4


    skip = 0
    for i in range(num_blocks):
        for r in [1, 2, 4, 8, 16]:
            l1, s = res_block(l1, r)
            skip += s

    #last layer
    logit = tf.nn.conv1d(skip, shape2, 1, padding='SAME')
    logit = tf.tanh(logit)
    logit = tf.nn.conv1d(logit, shape3, 1, padding='SAME')

    #reshaping to feed it into ctc_loss and ctc_greedy_decoder
    logit = tf.transpose(logit, (1, 0, 2))

    loss = tf.nn.ctc_loss(targets, logit, seq_len, ignore_longer_outputs_than_inputs=True)
    cost = tf.reduce_mean(loss)

    # optimizer = tf.train.MomentumOptimizer(initial_learning_rate, momentum).minimize(cost)
    optimizer = tf.train.AdamOptimizer(initial_learning_rate).minimize(cost)

    # Option 2: tf.contrib.ctc.ctc_beam_search_decoder
    # (it's slower but you'll get better results)
    decoded, log_prob = tf.nn.ctc_greedy_decoder(logit, seq_len)

    # Inaccuracy: label error rate
    ler = tf.reduce_mean(tf.edit_distance(tf.cast(decoded[0], tf.int32), targets))

#running the graph after building it completely (feeding the actual data in the model)
with tf.Session(graph=graph) as session:
    tf.global_variables_initializer().run()
    saver = tf.train.Saver()
    file = open('log.txt', 'w')
    #loop for number of epochs
    for curr_epoch in range(num_epochs):
        #loop for batches
        for batch in range(num_batches_per_epoch):
            indexes = [i % num_examples for i in range(batch * batch_size, (batch + 1) * batch_size)]
            batch_train_inputs, batch_train_seq_len = pad_sequences(train_inputs[indexes])
            batch_train_targets = sparse_tuple_from(train_targets[indexes])

            feed = {inputs: batch_train_inputs,
                    targets: batch_train_targets,
                    seq_len: batch_train_seq_len}
            #actually running the session to evaluate cost and also train our network
            batch_cost, _ = session.run([cost, optimizer], feed)
            train_cost += batch_cost * batch_size
            train_ler += session.run(ler, feed_dict=feed) * batch_size

        # Shuffle the data
        shuffled_indexes = np.random.permutation(num_examples)
        train_inputs = train_inputs[shuffled_indexes]
        train_targets = train_targets[shuffled_indexes]

        # Metrics mean
        train_cost /= num_examples
        train_ler /= num_examples
        #printing the results and also logging it in a file
        log = "Epoch {}/{}, train_cost = {:.3f}, train_ler = {:.3f}, time = {:.3f}"
        print(log.format(curr_epoch + 1, num_epochs, train_cost, train_ler, time.time() - start))
        file.write(log.format(curr_epoch + 1, num_epochs, train_cost, train_ler, time.time() - start) + '\n')

    '''
    for curr_epoch in range(num_epochs):
        train_cost = train_ler = 0
        start = time.time()
        indexes = np.random.choice(num_examples, size=batch_size, replace=False)
        batch_train_inputs, batch_train_seq_len = pad_sequences(train_inputs[indexes])
        batch_train_targets = sparse_tuple_from(train_targets[indexes])
    
        feed = {inputs: batch_train_inputs,
                targets: batch_train_targets,
                seq_len: batch_train_seq_len}
    
        batch_cost, _ = session.run([cost, optimizer], feed)
        train_cost += batch_cost * batch_size
        train_ler += session.run(ler, feed_dict=feed) * batch_size
    
        log = "Epoch {}/{}, train_cost = {:.3f}, train_ler = {:.3f}, time = {:.3f}"
        print(log.format(curr_epoch + 1, num_epochs, train_cost, train_ler, time.time() - start))
        file.write(log.format(curr_epoch + 1, num_epochs, train_cost, train_ler, time.time() - start) + '\n')
    
    print("model saving starts")
    saver.save(session, 'saved_models/final_model/s2t')
    print("model is saved")
'''
