
from shared.ops import *
from shared.util import *
import tensorflow as tf
def generator(config, y,z, reuse=False):
    x_dims = config['x_dims']
    with(tf.variable_scope("generator", reuse=reuse)):
        output_shape = x_dims[0]*x_dims[1]*config['channels']
        z_proj_dims = int(config['conv_g_layers'][0])*2
        z_dims = int(z.get_shape()[1])
        print("z_proj_dims", z_proj_dims, z_dims, config['y_dims'])
        noise_dims = z_proj_dims-z_dims-config['y_dims']
        print(noise_dims)
        if(noise_dims < 0):
            result = tf.concat(1, [y, z])
            result = linear(result, z_proj_dims, 'g_noise_proj')
            if(config['g_batch_norm']):
                result = batch_norm(config['batch_size'], name='g_noise_bn')(result)
            result = config['g_activation'](result)
        else:
            noise = tf.random_uniform([config['batch_size'], noise_dims],-1, 1)

            if(config['g_project'] == 'noise'):
                result = tf.concat(1, [y, z, noise])
            elif(config['g_project'] == 'zeros'):
                result = tf.concat(1, [y, z])
                #result = z
                result = tf.pad(result, [[0, 0],[noise_dims//2, noise_dims//2]])
            else:
                result = tf.concat(1, [y, z])
                #result = z
                result = linear(result, z_proj_dims, 'g_input_proj')

        def build_layers(result, z_proj_dims, offset):
            if config['conv_g_layers']:
                result = tf.reshape(result, [config['batch_size'], 4,4,z_proj_dims//16])
                #result = tf.nn.dropout(result, 0.7)
                for i, layer in enumerate(config['conv_g_layers']):
                    j=int(result.get_shape()[1]*2)
                    k=int(result.get_shape()[2]*2)
                    stride=2
                    if(j > x_dims[0]):
                        j = x_dims[0]
                        k = x_dims[1]
                        stride=1
                    output = [config['batch_size'], j,k,int(layer)]
                    result = deconv2d(result, output, name="g_conv_"+str(i+offset), k_w=config['conv_size'], k_h=config['conv_size'], d_h=stride, d_w=stride)
                    if(len(config['conv_g_layers']) == i+1):
                        print("Skipping last layer")
                    else:
                        print("Adding nonlinear")
                        if(config['g_batch_norm']):
                            result = batch_norm(config['batch_size'], name='g_conv_bn_'+str(i+offset))(result)
                        result = config['g_activation'](result)
                return result
        result = build_layers(result, z_proj_dims, 0)

        if(config['g_last_layer']):
            result = config['g_last_layer'](result)
        return result

def discriminator(config, x, z,g,gz, reuse=False):
    x_dims = config['x_dims']
    if(reuse):
        tf.get_variable_scope().reuse_variables()
    batch_size = config['batch_size']*2
    single_batch_size = config['batch_size']
    x = tf.concat(0, [x,g])
    z = tf.concat(0, [z,gz])
    x = tf.reshape(x, [batch_size, -1, config['channels']])
    if(config['d_add_noise']):
        x += tf.random_normal(x.get_shape(), mean=0, stddev=0.1)

    channels = (config['channels']+1)

    if(config['d_project'] == 'zeros'):
        noise_dims = int(x.get_shape()[1])-int(z.get_shape()[1])
        z = tf.pad(z, [[0, 0],[noise_dims//2, noise_dims//2]])
        z = tf.reshape(z, [batch_size, int(x.get_shape()[1]), 1])
        print("CONCAT", x.get_shape(), z.get_shape())
        result = tf.concat(2, [x,z])
    else:
        x = tf.reshape(x, [batch_size, -1])
        result = tf.concat(1, [z,x])
        result = linear(result, x_dims[0]*x_dims[1]*channels, scope='d_z')
        result = config['d_activation'](result)

    if config['conv_d_layers']:
        result = tf.reshape(result, [batch_size, x_dims[0],x_dims[1],channels])
        for i, layer in enumerate(config['conv_d_layers']):
            filter = config['d_conv_size']
            stride = 2
            if(filter > result.get_shape()[1]):
                filter = int(result.get_shape()[1])
                stride = 1
            result = conv2d(result, layer, name='d_conv'+str(i), k_w=filter, k_h=filter, d_h=stride, d_w=stride)
            if(config['d_batch_norm']):
                result = batch_norm(batch_size, name='d_conv_bn_'+str(i))(result)
            result = config['d_activation'](result)
        result = tf.reshape(x, [batch_size, -1])

    def get_minibatch_features(h):
        n_kernels = int(config['d_kernels'])
        dim_per_kernel = int(config['d_kernel_dims'])
        x = linear(h, n_kernels * dim_per_kernel, scope="d_h")
        activation = tf.reshape(x, (batch_size, n_kernels, dim_per_kernel))

        big = np.zeros((batch_size, batch_size), dtype='float32')
        big += np.eye(batch_size)
        big = tf.expand_dims(big, 1)

        abs_dif = tf.reduce_sum(tf.abs(tf.expand_dims(activation,3) - tf.expand_dims(tf.transpose(activation, [1, 2, 0]), 0)), 2)
        mask = 1. - big
        masked = tf.exp(-abs_dif) * mask
        def half(tens, second):
            m, n, _ = tens.get_shape()
            m = int(m)
            n = int(n)
            return tf.slice(tens, [0, 0, second * single_batch_size], [m, n, single_batch_size])
        # TODO: speedup by allocating the denominator directly instead of constructing it by sum
        #       (current version makes it easier to play with the mask and not need to rederive
        #        the denominator)
        f1 = tf.reduce_sum(half(masked, 0), 2) / tf.reduce_sum(half(mask, 0))
        f2 = tf.reduce_sum(half(masked, 1), 2) / tf.reduce_sum(half(mask, 1))

        return [f1, f2]
    minis = get_minibatch_features(result)
    g_proj = tf.concat(1, [result]+minis)

    #result = tf.nn.dropout(result, 0.7)
    if(config['d_linear_layer']):
        result = linear(result, config['d_linear_layers'], scope="d_linear_layer")
        result = config['d_activation'](result)

    last_layer = result
    result = linear(result, config['y_dims']+1, scope="d_proj")


    def build_logits(class_logits, num_classes):

        generated_class_logits = tf.squeeze(tf.slice(class_logits, [0, num_classes - 1], [batch_size, 1]))
        positive_class_logits = tf.slice(class_logits, [0, 0], [batch_size, num_classes - 1])

        """
        # make these a separate matmul with weights initialized to 0, attached only to generated_class_logits, or things explode
        generated_class_logits = tf.squeeze(generated_class_logits) + tf.squeeze(linear(diff_feat, 1, stddev=0., scope="d_indivi_logits_from_diff_feat"))
        assert len(generated_class_logits.get_shape()) == 1
        # re-assemble the logits after incrementing the generated class logits
        class_logits = tf.concat(1, [positive_class_logits, tf.expand_dims(generated_class_logits, 1)])
        """

        mx = tf.reduce_max(positive_class_logits, 1, keep_dims=True)
        safe_pos_class_logits = positive_class_logits - mx

        gan_logits = tf.log(tf.reduce_sum(tf.exp(safe_pos_class_logits), 1)) + tf.squeeze(mx) - generated_class_logits
        assert len(gan_logits.get_shape()) == 1

        return class_logits, gan_logits
    num_classes = config['y_dims'] +1
    class_logits, gan_logits = build_logits(result, num_classes)
    print("Class logits gan logits", class_logits, gan_logits)
    return [tf.slice(class_logits, [0, 0], [single_batch_size, num_classes]),
                tf.slice(gan_logits, [0], [single_batch_size]),
                tf.slice(class_logits, [single_batch_size, 0], [single_batch_size, num_classes]),
                tf.slice(gan_logits, [single_batch_size], [single_batch_size]), 
                last_layer]


def build_conv_tower(result, layers, filter, batch_size, batch_norm_enabled, name, activation):
    for i, layer in enumerate(layers):
        print('-!-', result, tf.reshape(result, [batch_size, -1]))
        print(layer)
        stride = 2
        if filter > result.get_shape()[2]:
            filter = int(result.get_shape()[2])
            stride = 1
        result = conv2d(result, layer, name=name+str(i), k_w=filter, k_h=filter, d_h=stride, d_w=stride)
        if(batch_norm_enabled):
            result = batch_norm(batch_size, name=name+'_bn_'+str(i))(result)
        if(len(layers) == i+1):
            print("Skipping last layer")
        else:
            print("Adding nonlinear")
            result = activation(result)
        print(tf.reshape(result, [batch_size, -1]))
    result = tf.reshape(result, [batch_size, -1])
    return result


def encoder(config, x,y, z,z_mu,z_sigma):
    x_dims = config['x_dims']
    deconv_shape = None
    output_shape = config['z_dim']
    x = tf.reshape(x, [config["batch_size"], -1,config['channels']])
    noise_dims = int(x.get_shape()[1])-int(y.get_shape()[1])
    channels = (config['channels']+1)
    if(config['e_project'] == 'zeros'):
        #y = tf.concat(1, [y, z, z_mu, z_sigma])
        noise_dims = int(x.get_shape()[1])-int(y.get_shape()[1])
        y = tf.concat(1, [y, tf.zeros([config['batch_size'], noise_dims])])
        #y = tf.pad(y, [[0, 0],[noise_dims//2, noise_dims//2]])
    elif(config['e_project'] == 'noise'):
        noise = tf.random_uniform([config['batch_size'], noise_dims],-1, 1)
        y = tf.concat(1, [y, noise])
    else:
        y = linear(y, int(x.get_shape()[1]), scope='g_y')
 
    y = tf.reshape(y, [config['batch_size'], int(x.get_shape()[1]), 1])
    result = tf.concat(2, [x,y])
    result = tf.reshape(result, [config["batch_size"], x_dims[0],x_dims[1],channels])

    if config['g_encode_layers']:
        result = build_conv_tower(result, config['g_encode_layers'], config['e_conv_size'], config['batch_size'], config['d_batch_norm'], 'g_encoder_conv_', config['e_activation'])

    if(result.get_shape()[1] != output_shape):
        print("(e)Adding linear layer", result.get_shape(), output_shape)
        result = config['e_activation'](result)
        result = linear(result, output_shape, scope="g_enc_proj")
        if(config['g_batch_norm']):
            result = batch_norm(config['batch_size'], name='g_encoder_bn_lin')(result)

    if(config['e_last_layer']):
        result = config['e_last_layer'](result)
    return result

def approximate_z(config, x, y):
    x_dims = config['x_dims']
    transfer_fct = config['transfer_fct']
    x = tf.reshape(x, [config["batch_size"], -1,config['channels']])
    noise_dims = int(x.get_shape()[1])-int(y.get_shape()[1])
    n_input = config['n_input']
    n_hidden_recog_1 = int(config['n_hidden_recog_1'])
    n_hidden_recog_2 = int(config['n_hidden_recog_2'])
    n_z = int(config['z_dim'])
    channels = (config['channels']+1)
    if(config['e_project'] == 'zeros'):
        noise_dims = int(x.get_shape()[1])-config['y_dims']
        #y = tf.pad(y, [[0, 0],[noise_dims//2, noise_dims//2]])
        noise = tf.zeros([config['batch_size'], noise_dims])
        result = tf.concat(1, [tf.reshape(x, [config['batch_size'], -1]), y, noise])
        #y = tf.reshape(y, [config['batch_size'], int(x.get_shape()[1]), 1])
    #result = tf.concat(2, [x,y])
    print(result)
    result = tf.reshape(result, [config["batch_size"], x_dims[0],x_dims[1],channels])

    if config['g_encode_layers']:
        result = build_conv_tower(result, config['g_encode_layers'], config['e_conv_size'], config['batch_size'], config['d_batch_norm'], 'g_vae_', transfer_fct)

    result = transfer_fct(result)

    b_out_mean= tf.get_variable('g_b_out_mean', initializer=tf.zeros([n_z], dtype=tf.float32))
    out_mean= tf.get_variable('g_out_mean', [result.get_shape()[1], n_z], initializer=tf.contrib.layers.xavier_initializer())
    mu = tf.add(tf.matmul(result, out_mean),b_out_mean)

    out_log_sigma=tf.get_variable('g_out_log_sigma', [result.get_shape()[1], n_z], initializer=tf.contrib.layers.xavier_initializer())
    b_out_log_sigma= tf.get_variable('g_b_out_log_sigma', initializer=tf.zeros([n_z], dtype=tf.float32))
    sigma = tf.add(tf.matmul(result, out_log_sigma),b_out_log_sigma)

    e_projected_z=tf.get_variable('g_encoded_z', [result.get_shape()[1], n_z], initializer=tf.contrib.layers.xavier_initializer())
    b_encoded_z= tf.get_variable('g_b_encoded_z', initializer=tf.zeros([n_z], dtype=tf.float32))
    e_z = tf.add(tf.matmul(result, e_projected_z),b_encoded_z)

    n_z = int(config["z_dim"])
    eps = tf.random_normal((config['batch_size'], n_z), 0, 1, 
                           dtype=tf.float32)

    z = tf.add(mu, tf.mul(tf.sqrt(tf.exp(sigma)), eps))
    z = batch_norm(config['batch_size'], name='g_e_z_bn')(z)

    e_z = batch_norm(config['batch_size'], name='g_e_ez_bn')(e_z)

    if(config['e_last_layer']):
        z = config['e_last_layer'](z)
        e_z = config['e_last_layer'](e_z)
    return e_z, z, mu, sigma
def sigmoid_kl_with_logits(logits, targets):
    print(targets)
    # broadcasts the same target value across the whole batch
    # this is implemented so awkwardly because tensorflow lacks an x log x op
    assert isinstance(targets, float)
    if targets in [0., 1.]:
        entropy = 0.
    else:
        entropy = - targets * np.log(targets) - (1. - targets) * np.log(1. - targets)
    return tf.nn.sigmoid_cross_entropy_with_logits(logits, tf.ones_like(logits) * targets) - entropy


def create(config, x,y):
    batch_size = config["batch_size"]
    print(y)

    #x = x/tf.reduce_max(tf.abs(x), 0)
    encoded_z, z, z_mu, z_sigma = approximate_z(config, x, y)
    #encoded_z = encoder(config, x,y,z,z_mu,z_sigma)

    print("Build generator")
    g = generator(config, y, z)
    print("Build encoder")
    encoded = generator(config, y, encoded_z, reuse=True)
    print("shape of g,x", g.get_shape(), x.get_shape())
    print("shape of z,encoded_z", z.get_shape(), encoded_z.get_shape())
    d_real, d_real_sig, d_fake, d_fake_sig, d_last_layer = discriminator(config,x, encoded_z, g, z, reuse=False)

    latent_loss = -config['latent_lambda'] * tf.reduce_mean(1 + z_sigma
                                       - tf.square(z_mu)
                                       - tf.exp(z_sigma), 1)
    np_fake = np.array([0]*config['y_dims']+[1])
    print('np_fake', np_fake)
    fake_symbol = tf.tile(tf.constant(np_fake, dtype=tf.float32), [config['batch_size']])
    fake_symbol = tf.reshape(fake_symbol, [config['batch_size'],config['y_dims']+1])

    real_symbols = tf.concat(1, [y, tf.zeros([config['batch_size'], 1])])
    #real_symbols = y


    if(config['loss'] == 'softmax'):
        d_fake_loss = tf.nn.softmax_cross_entropy_with_logits(d_fake, fake_symbol)
        d_real_loss = tf.nn.softmax_cross_entropy_with_logits(d_real, real_symbols)

        g_loss= tf.nn.softmax_cross_entropy_with_logits(d_fake, real_symbols)

    else:
        zeros = tf.zeros_like(d_fake_sig)
        ones = tf.zeros_like(d_real_sig)

        #d_fake_loss = tf.nn.sigmoid_cross_entropy_with_logits(d_fake, zeros)
        #d_real_loss = tf.nn.sigmoid_cross_entropy_with_logits(d_real, ones)

        generator_target_prob = config['g_target_prob']
        d_label_smooth = config['d_label_smooth']
        d_fake_loss = tf.nn.sigmoid_cross_entropy_with_logits(d_fake_sig, zeros)
        #d_real_loss = tf.nn.sigmoid_cross_entropy_with_logits(d_real_sig, ones)
        d_real_loss = sigmoid_kl_with_logits(d_real_sig, 1.-d_label_smooth)
        d_class_loss = tf.nn.softmax_cross_entropy_with_logits(d_real,real_symbols)
        d_fake_class_loss = tf.nn.softmax_cross_entropy_with_logits(d_fake,fake_symbol)

        g_loss= sigmoid_kl_with_logits(d_fake_sig, generator_target_prob)
        g_class_loss = tf.nn.softmax_cross_entropy_with_logits(d_fake, real_symbols)

        #g_loss_encoder = tf.nn.sigmoid_cross_entropy_with_logits(d_real, zeros)
        #TINY = 1e-12
        #d_real = tf.nn.sigmoid(d_real)
        #d_fake = tf.nn.sigmoid(d_fake)
        #d_fake_loss = -tf.log(1-d_fake+TINY)
        #d_real_loss = -tf.log(d_real+TINY)
        #g_loss_softmax = -tf.log(1-d_real+TINY)
        #g_loss_encoder = -tf.log(d_fake+TINY)
    if(config['latent_loss']):
        g_loss = tf.reduce_mean(g_loss)+tf.reduce_mean(latent_loss)+tf.reduce_mean(g_class_loss)
    else:
        g_loss = tf.reduce_mean(g_loss)+tf.reduce_mean(g_class_loss)
    d_loss = tf.reduce_mean(d_fake_loss) + tf.reduce_mean(d_real_loss) + \
            tf.reduce_mean(d_class_loss)+tf.reduce_mean(d_fake_class_loss)
    print('d_loss', d_loss.get_shape())



    if config['regularize']:
        ws = None
        with tf.variable_scope("generator"):
            with tf.variable_scope("g_conv_0"):
                tf.get_variable_scope().reuse_variables()
                ws = tf.get_variable('w')
                tf.get_variable_scope().reuse_variables()
                b = tf.get_variable('biases')
            lam = config['regularize_lambda']
            g_loss += lam*tf.nn.l2_loss(ws)+lam*tf.nn.l2_loss(b)


    mse_loss = tf.reduce_max(tf.square(x-encoded))
    if config['mse_loss']:
        mse_lam = config['mse_lambda']
        g_loss += mse_lam * mse_loss

    g_vars = [var for var in tf.trainable_variables() if 'g_' in var.name]
    d_vars = [var for var in tf.trainable_variables() if 'd_' in var.name]

    print(config);
    print('vars', [v.name for v in tf.trainable_variables()])
    g_optimizer = tf.train.AdamOptimizer(np.float32(config['g_learning_rate'])).minimize(g_loss, var_list=g_vars)
    d_optimizer = tf.train.AdamOptimizer(np.float32(config['d_learning_rate'])).minimize(d_loss, var_list=d_vars)

    mse_optimizer = tf.train.AdamOptimizer(np.float32(config['g_learning_rate'])).minimize(mse_loss, var_list=tf.trainable_variables())

    set_tensor("x", x)
    set_tensor("y", y)
    set_tensor("g_loss", g_loss)
    set_tensor("d_loss", d_loss)
    set_tensor("g_optimizer", g_optimizer)
    set_tensor("d_optimizer", d_optimizer)
    set_tensor("mse_optimizer", mse_optimizer)
    set_tensor("g", g)
    set_tensor("encoded", encoded)
    set_tensor("encoder_mse", mse_loss)
    set_tensor("d_fake", tf.reduce_mean(d_fake))
    set_tensor("d_real", tf.reduce_mean(d_real))
    set_tensor("d_fake_loss", tf.reduce_mean(d_fake_loss))
    set_tensor("d_real_loss", tf.reduce_mean(d_real_loss))
    set_tensor("d_class_loss", tf.reduce_mean(d_real_loss))
    set_tensor("g_class_loss", tf.reduce_mean(g_class_loss))
    set_tensor("d_loss", tf.reduce_mean(d_real_loss))

def train(sess, config):
    x = get_tensor('x')
    g = get_tensor('g')
    g_loss = get_tensor("g_loss")
    d_loss = get_tensor("d_loss")
    d_fake_loss = get_tensor('d_fake_loss')
    d_real_loss = get_tensor('d_real_loss')
    g_optimizer = get_tensor("g_optimizer")
    d_optimizer = get_tensor("d_optimizer")
    d_class_loss = get_tensor("d_class_loss")
    g_class_loss = get_tensor("g_class_loss")
    mse_optimizer = get_tensor("mse_optimizer")
    encoder_mse = get_tensor("encoder_mse")
    _, d_cost = sess.run([d_optimizer, d_loss])
    _, g_cost, x, g,e_loss,d_fake,d_real, d_class, g_class = sess.run([g_optimizer, g_loss, x, g, encoder_mse,d_fake_loss, d_real_loss, d_class_loss, g_class_loss])
    #_ = sess.run([mse_optimizer])

    print("g cost %.2f d cost %.2f encoder %.2f d_fake %.6f d_real %.2f d_class %.2f g_class %.2f" % (g_cost, d_cost,e_loss, d_fake, d_real, d_class, g_class))
    print("X mean %.2f max %.2f min %.2f" % (np.mean(x), np.max(x), np.min(x)))
    print("G mean %.2f max %.2f min %.2f" % (np.mean(g), np.max(g), np.min(g)))

    return d_cost, g_cost

def test(sess, config):
    x = get_tensor("x")
    y = get_tensor("y")
    d_fake = get_tensor("d_fake")
    d_real = get_tensor("d_real")
    g_loss = get_tensor("g_loss")
    encoder_mse = get_tensor("encoder_mse")

    g_cost, d_fake_cost, d_real_cost, e_cost = sess.run([g_loss, d_fake, d_real, encoder_mse])


    #hc.event(costs, sample_image = sample[0])

    #print("test g_loss %.2f d_fake %.2f d_loss %.2f" % (g_cost, d_fake_cost, d_real_cost))
    return g_cost,d_fake_cost, d_real_cost, e_cost


