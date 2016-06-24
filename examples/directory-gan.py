import hyperchamber as hc
from shared.ops import *
from shared.util import *
from shared.gan import *
from shared.gan import *
from shared.gan import *
import shared
import json

import shared.data_loader
import os
import sys
import time
import numpy as np
import tensorflow
import tensorflow as tf
import copy

import matplotlib
import matplotlib.pyplot as plt

from tensorflow.python.framework import ops

from tensorflow.models.image.cifar10 import cifar10_input
import shared.cifar_utils as cifar_utils
import argparse

parser = argparse.ArgumentParser(description='Runs the GAN.')
parser.add_argument('--load_config', type=str)
parser.add_argument('--epochs', type=int, default=10)

parser.add_argument('--channels', type=int, default=3)
parser.add_argument('--directory', type=str)
parser.add_argument('--no_stop', type=bool)
parser.add_argument('--crop', type=bool, default=True)

parser.add_argument('--width', type=int, default=64)
parser.add_argument('--height', type=int, default=64)

args = parser.parse_args()
start=.00001
end=.002
num=1000
hc.set("g_learning_rate", list(np.linspace(start, end, num=num)))
hc.set("d_learning_rate", list(np.linspace(start, end, num=num)))

hc.set("n_hidden_recog_1", list(np.linspace(100, 1000, num=100)))
hc.set("n_hidden_recog_2", list(np.linspace(100, 1000, num=100)))
hc.set("transfer_fct", [tf.nn.elu, tf.nn.relu, tf.nn.relu6, lrelu, maxout, offset_maxout]);
hc.set("d_activation", [tf.nn.elu, tf.nn.relu, tf.nn.relu6, lrelu, maxout, offset_maxout]);
hc.set("g_activation", [tf.nn.elu, tf.nn.relu, tf.nn.relu6, lrelu, maxout, offset_maxout]);
hc.set("e_activation", [tf.nn.elu, tf.nn.relu, tf.nn.relu6, lrelu]);
hc.set("g_last_layer", [tf.nn.tanh]);
hc.set("e_last_layer", [tf.nn.tanh]);

hc.set('d_add_noise', [True])

hc.set("n_input", 64*64*3)

conv_g_layers = [[i*8, i*4] for i in [16,32]]
conv_g_layers = [[i*8, i*4, i*2] for i in [16,32]]
conv_g_layers += [[i*16, i*8, i*4, i*2] for i in [8, 16]]
conv_g_layers += [[i*16, i*8, i*4, i*2, i] for i in [4, 6, 8]]

conv_g_layers+=[[i*16,i*8, i*4] for i in list(np.arange(2, 16))]

conv_d_layers = [[i, i*2, i*4, i*8] for i in list(np.arange(32, 128))] 
conv_d_layers += [[i, i*2, i*4, i*8] for i in list(np.arange(16,32))] 
conv_d_layers += [[i, i*2, i*4, i*8, i*16] for i in [12, 16, 32, 64]] 
#conv_d_layers = [[32, 32*2, 32*4],[32, 64, 64*2],[64,64*2], [16,16*2, 16*4], [16,16*2]]

hc.set("conv_size", [3, 4, 5])
hc.set("d_conv_size", [3, 4, 5])
hc.set("e_conv_size", [3, 4, 5])
hc.set("conv_g_layers", conv_g_layers)
hc.set("conv_d_layers", conv_d_layers)

g_encode_layers = [[i, i*2, i*4, i*8] for i in list(np.arange(8, 32))] 
hc.set("g_encode_layers", g_encode_layers)

hc.set("z_dim", list(np.arange(2,300)))

hc.set("regularize", [True])
hc.set("regularize_lambda", list(np.linspace(0.0001, 1, num=30)))

hc.set("g_batch_norm", [True])
hc.set("d_batch_norm", [True])

hc.set("g_encoder", [True])

hc.set('d_linear_layer', [True])
hc.set('d_linear_layers', list(np.arange(50, 600)))

hc.set("g_target_prob", list(np.linspace(.75 /2., .85 /2., num=10))+list(np.linspace(.65 /2., .75/2, num=10)))
hc.set("d_label_smooth", list(np.linspace(0.25, 0.35, num=10)) + list(np.linspace(.15,.25,num=10)))

hc.set("d_kernels", list(np.arange(25, 80)))
hc.set("d_kernel_dims", list(np.arange(200, 400)))

hc.set("loss", ['custom'])

hc.set("mse_loss", [False])
hc.set("mse_lambda",list(np.linspace(0.0001, 0.1, num=30)))

hc.set("latent_loss", [True])
hc.set("latent_lambda", list(np.linspace(0.01, .5, num=30)))
hc.set("g_dropout", list(np.linspace(0.6, 0.99, num=30)))

hc.set("g_project", ['noise'])
hc.set("d_project", ['zeros'])
hc.set("e_project", ['zeros'])

BATCH_SIZE=64
hc.set("batch_size", BATCH_SIZE)
hc.set("model", "martyn/fonts:0.1")
hc.set("version", "0.0.1")
hc.set("machine", "martyn")


def sample_input(sess, config):
    x = get_tensor("x")
    y = get_tensor("y")
    encoded = get_tensor('encoded')
    sample, encoded, label = sess.run([x, encoded, y])
    return sample[0], encoded[0], label[0]


def split_sample(n, sample, x_dims, channels):
    return [np.reshape(sample[0+i:1+i], [x_dims[0],x_dims[1], channels]) for i in range(n)]
def samples(sess, config):
    generator = get_tensor("g")
    y = get_tensor("y")
    x = get_tensor("x")
    rand = np.random.randint(0,config['y_dims'], size=config['batch_size'])
    random_one_hot = np.eye(config['y_dims'])[rand]
    sample = sess.run(generator, feed_dict={y:random_one_hot})
    #sample =  np.concatenate(sample, axis=0)
    return split_sample(10, sample, config['x_dims'], config['channels'])

def plot_mnist_digit(config, image, file):
    """ Plot a single MNIST image."""
    fig = plt.figure()
    ax = fig.add_subplot(1, 1, 1)
    ax.matshow(image, cmap = matplotlib.cm.binary)
    plt.xticks(np.array([]))
    plt.yticks(np.array([]))
    #plt.suptitle(config)
    plt.savefig(file)

def epoch(sess, config):
    batch_size = config["batch_size"]
    n_samples =  config['examples_per_epoch']
    total_batch = int(n_samples / batch_size)
    for i in range(total_batch):
        d_loss, g_loss = train(sess, config)
        if(i > 10 and not args.no_stop):
        
            if(math.isnan(d_loss) or math.isnan(g_loss) or g_loss < -10 or g_loss > 1000 or d_loss > 1000):
                return False
        
            g = get_tensor('g')
            rX = sess.run([g])
            if(np.min(rX) < -1000 or np.max(rX) > 1000):
                return False


    return True

def test_config(sess, config):
    batch_size = config["batch_size"]
    n_samples =  batch_size*10
    total_batch = int(n_samples / batch_size)
    results = []
    for i in range(total_batch):
        results.append(test(sess, config))
    return results

def collect_measurements(epoch, sess, config):
    return {
            'epoch': epoch
            }

def test_epoch(epoch, j, sess, config):
    x, encoded, label = sample_input(sess, config)
    sample_file = "samples/input-"+str(j)+".png"
    cifar_utils.plot(config, x, sample_file)
    encoded_sample = "samples/encoded-"+str(j)+".png"
    cifar_utils.plot(config, encoded, encoded_sample)

    def to_int(one_hot):
        i = 0
        for l in list(one_hot):
            if(l>0.5):
                return i
            i+=1
        return None
    
    sample_file = {'image':sample_file, 'label':json.dumps(to_int(label))}
    encoded_sample = {'image':encoded_sample, 'label':'reconstructed'}
    sample = samples(sess, config)
    sample_list = [sample_file, encoded_sample]
    for s in sample:
        sample_file = "samples/config-"+str(j)+".png"
        cifar_utils.plot(config, s, sample_file)
        sample_list.append({'image':sample_file,'label':'sample-'+str(j)})
        j+=1
    print("Creating sample")
    measurements = collect_measurements(epoch, sess, config)
    hc.io.sample(config, sample_list, measurements)
    return j

def record_run(config):
    results = test_config(sess, config)
    loss = np.array(results)
    #results = np.reshape(results, [results.shape[1], results.shape[0]])
    g_loss = [g for g,_,_,_ in loss]
    g_loss = np.mean(g_loss)
    d_fake = [d_ for _,d_,_,_ in loss]
    d_fake = np.mean(d_fake)
    d_real = [d for _,_,d,_ in loss]
    d_real = np.mean(d_real)
    e_loss = [e for _,_,_,e in loss]
    e_loss = np.mean(e_loss)

    # calculate D.difficulty = reduce_mean(d_loss_fake) - reduce_mean(d_loss_real)
    difficulty = d_real * (1-d_fake)
    # calculate G.ranking = reduce_mean(g_loss) * D.difficulty
    ranking = g_loss * (1.0-difficulty)

    ranking = e_loss
    results =  {
        'difficulty':float(difficulty),
        'ranking':float(ranking),
        'g_loss':float(g_loss),
        'd_fake':float(d_fake),
        'd_real':float(d_real),
        'e_loss':float(e_loss)
    }
    print("Recording ", results)
    hc.io.record(config, results)





print("Generating configs with hyper search space of ", hc.count_configs())

j=0
k=0

def get_function(name):
    if not isinstance(name, str):
        return name
    print('name', name);
    if(name == "function:tensorflow.python.ops.gen_nn_ops.relu"):
        return tf.nn.relu
    if(name == "function:tensorflow.python.ops.nn_ops.relu"):
        return tf.nn.relu
    if(name == "function:tensorflow.python.ops.gen_nn_ops.relu6"):
        return tf.nn.relu6
    if(name == "function:tensorflow.python.ops.nn_ops.relu6"):
        return tf.nn.relu6
    if(name == "function:tensorflow.python.ops.gen_nn_ops.elu"):
        return tf.nn.elu
    if(name == "function:tensorflow.python.ops.nn_ops.elu"):
        return tf.nn.elu
    if(name == "function:tensorflow.python.ops.math_ops.tanh"):
        return tf.nn.tanh
    return eval(name.split(":")[1])
for config in hc.configs(1):
    other_config = copy.copy(config)
    if(args.load_config):
        print("Loading config", args.load_config)
        config.update(hc.io.load_config(args.load_config))
        if(not config):
            print("Could not find config", args.load_config)
            break
    config['g_activation']=get_function(config['g_activation'])
    config['d_activation']=get_function(config['d_activation'])
    config['e_activation']=get_function(config['e_activation'])
    config['transfer_fct']=get_function(config['transfer_fct'])
    #config['last_layer']=get_function(config['last_layer'])
    config['g_last_layer']=get_function(config['g_last_layer'])
    config['e_last_layer']=get_function(config['e_last_layer'])
    config['g_encode_layers']=other_config['g_encode_layers']
    config['e_conv_size']=other_config['e_conv_size']
    config['z_dim']=other_config['z_dim']
    config['mse_loss']=True#other_config['mse_loss']
    print(config)
    print("Testing configuration", config)
    print("TODO: TEST BROKEN")
    sess = tf.Session()
    format = 'png'
    channels = args.channels
    crop = args.crop
    train_x,train_y, num_labels,examples_per_epoch = shared.data_loader.labelled_image_tensors_from_directory(args.directory,config['batch_size'], channels=channels, format=format,crop=crop)
    config['y_dims']=num_labels
    config['x_dims']=[64,64]
    config['channels']=channels
    config['conv_g_layers'].append(channels)
    config['examples_per_epoch']=examples_per_epoch
    x = train_x
    y = train_y
    y=tf.one_hot(tf.cast(train_y,tf.int64), config['y_dims'], 1.0, 0.0)
    graph = create(config,x,y)
    init = tf.initialize_all_variables()
    sess.run(init)

    tf.train.start_queue_runners(sess=sess)



    #tf.assign(x,train_x)
    #tf.assign(y,tf.one_hot(tf.cast(train_y,tf.int64), Y_DIMS, 1.0, 0.0))
    sampled=False
    print("Running for ", args.epochs, " epochs")
    for i in range(args.epochs):
        if(not epoch(sess, config)):
            print("Epoch failed")
            break
        j=test_epoch(i, j, sess, config)
        if(i == args.epochs-1):
            print("Recording run...")
            record_run(config)
    #x.assign(test_x)
    #y.assign(tf.one_hot(tf.cast(test_y,tf.int64), Y_DIMS, 1.0, 0.0))
    #print("results: difficulty %.2f, ranking %.2f, g_loss %.2f, d_fake %.2f, d_real %.2f" % (difficulty, ranking, g_loss, d_fake, d_real))

    #with g.as_default():
    tf.reset_default_graph()
    sess.close()


def by_ranking(x):
    config,result = x
    return result['ranking']

for config, result in hc.top(by_ranking):
    print("RESULTS")
    print(config, result)

    #print("Done testing.  Final cost was:", hc.cost())

print("Done")

#for gold, silver, bronze in hc.top_configs(3):

