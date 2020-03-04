import numpy as np
import platform
import os
import time
import argparse
from astropy.io import fits

os.environ["KERAS_BACKEND"] = "tensorflow"

if (platform.node() != 'vena'):
	os.environ["CUDA_VISIBLE_DEVICES"] = "0"

import tensorflow as tf

tf.disable_v2_behavior()
import keras.backend.tensorflow_backend as ktf
from keras.layers import Input, Conv2D, Activation, BatchNormalization, Concatenate, Dropout, UpSampling2D
from keras.models import Model
# IDL
import idlsave


class deepvel(object):
	
	def __init__(self, observations, output, border_x1=0, border_x2=0, border_y1=0, border_y2=0, read_ic1_median=0):
		"""

		Parameters
		----------
		observations : array
			Array of size (n_times, nx, ny) with the n_times consecutive images of size nx x ny
		output : string
			Filename were the output is saved
		border : int (optional)
			Portion of the borders to be removed during computations. This is useful if images are
			apodized
		"""
		
		# Only allocate needed memory with Tensorflow
		config = tf.compat.v1.ConfigProto()
		config.gpu_options.allow_growth = True
		session = tf.compat.v1.Session(config=config)
		# ktf.set_session(session)
		
		self.border_x1 = border_x1
		self.border_x2 = border_x2
		self.border_y1 = border_y1
		self.border_y2 = border_y2
		n_timesteps, nx, ny = observations.shape
		
		self.n_frames = n_timesteps - 1
		
		self.nx = nx - self.border_x1 - self.border_x2
		self.ny = ny - self.border_y1 - self.border_y2
		
		self.n_times = 2
		self.n_filters = 64
		self.kernel_size = 3
		self.batch_size = 1
		self.observations = observations
		self.output = output
		
		self.ic1_read_median = read_ic1_median
		tmp = np.load('network/Stagger_normalization.npz')
		
		self.ic1_min = tmp['min_ic']
		self.ic1_max = tmp['max_ic']
		self.ic1_mean = tmp['mean_ic']
		self.ic1_median = tmp['median_ic']
		self.ic1_stddev = tmp['stddev_ic']
		self.vv_min = tmp['min_v']
		self.vv_max = tmp['max_v']
		self.vv_mean = tmp['mean_v']
		self.vv_median = tmp['median_v']
		self.vv_stddev = tmp['stddev_v']
	
	def define_network(self):
		print("Setting up network...")
		
		inputs = Input(shape=(self.nx, self.ny, self.n_times))
		x = inputs

		conv1 = Conv2D(self.n_filters, (self.kernel_size, self.kernel_size), strides=(1, 1), padding='same', init='he_normal')(x)
		conv1 = BatchNormalization()(conv1)
		conv1 = Activation('relu')(conv1)
		stri1 = Conv2D(self.n_filters, (self.kernel_size, self.kernel_size), strides=(2, 2), padding='same', init='he_normal')(conv1)
		stri1 = BatchNormalization()(stri1)
		stri1 = Activation('relu')(stri1)
		
		conv2 = Conv2D(2 * self.n_filters, (self.kernel_size, self.kernel_size), strides=(1, 1), padding='same', init='he_normal')(stri1)
		conv2 = BatchNormalization()(conv2)
		conv2 = Activation('relu')(conv2)
		stri2 = Conv2D(2 * self.n_filters, (self.kernel_size, self.kernel_size), strides=(2, 2), padding='same', init='he_normal')(conv2)
		stri2 = BatchNormalization()(stri2)
		stri2 = Activation('relu')(stri2)
		
		conv3 = Conv2D(2 * self.n_filters, (self.kernel_size, self.kernel_size), strides=(1, 1), padding='same', init='he_normal')(stri2)
		conv3 = BatchNormalization()(conv3)
		conv3 = Activation('relu')(conv3)
		stri3 = Conv2D(2 * self.n_filters, (self.kernel_size, self.kernel_size), strides=(2, 2), padding='same', init='he_normal')(conv3)
		stri3 = BatchNormalization()(stri3)
		stri3 = Activation('relu')(stri3)
		
		convc = Conv2D(4 * self.n_filters, (self.kernel_size, self.kernel_size), strides=(1, 1), padding='same', init='he_normal')(stri3)
		convc = BatchNormalization()(convc)
		convc = Activation('relu')(convc)
		convc = Conv2D(4 * self.n_filters, (self.kernel_size, self.kernel_size), strides=(1, 1), padding='same', init='he_normal')(convc)
		convc = BatchNormalization()(convc)
		convc = Activation('relu')(convc)
		
		upconv3 = Conv2D(2 * self.n_filters, (self.kernel_size, self.kernel_size), strides=(1, 1), activation='relu', padding='same', kernel_initializer='he_normal')(UpSampling2D(size=(2, 2))(convc))
		upconv3 = Concatenate(axis=3)([conv3, upconv3])
		upconv3 = Conv2D(2 * self.n_filters, (self.kernel_size, self.kernel_size), padding='same', init='he_normal')(upconv3)
		upconv3 = BatchNormalization()(upconv3)
		upconv3 = Activation('relu')(upconv3)
		upconv3 = Conv2D(2 * self.n_filters, (self.kernel_size, self.kernel_size), strides=(1, 1), padding='same', init='he_normal')(upconv3)
		upconv3 = BatchNormalization()(upconv3)
		upconv3 = Activation('relu')(upconv3)
		
		upconv2 = Conv2D(2 * self.n_filters, (self.kernel_size, self.kernel_size), strides=(1, 1), activation='relu', padding='same', kernel_initializer='he_normal')(UpSampling2D(size=(2, 2))(upconv3))
		upconv2 = Concatenate(axis=3)([conv2, upconv2])
		upconv2 = Conv2D(2 * self.n_filters, (self.kernel_size, self.kernel_size), padding='same', init='he_normal')(upconv2)
		upconv2 = BatchNormalization()(upconv2)
		upconv2 = Activation('relu')(upconv2)
		upconv2 = Conv2D(2 * self.n_filters, (self.kernel_size, self.kernel_size), strides=(1, 1), padding='same', init='he_normal')(upconv2)
		upconv2 = BatchNormalization()(upconv2)
		upconv2 = Activation('relu')(upconv2)
		
		upconv1 = Conv2D(self.n_filters, (self.kernel_size, self.kernel_size), strides=(1, 1), activation='relu', padding='same', kernel_initializer='he_normal')(UpSampling2D(size=(2, 2))(upconv2))
		upconv1 = Concatenate(axis=3)([conv1, upconv1])
		upconv1 = Conv2D(self.n_filters, (self.kernel_size, self.kernel_size), padding='same', init='he_normal')(upconv1)
		upconv1 = BatchNormalization()(upconv1)
		upconv1 = Activation('relu')(upconv1)
		upconv1 = Conv2D(self.n_filters, (self.kernel_size, self.kernel_size), strides=(1, 1), padding='same', init='he_normal')(upconv1)
		upconv1 = BatchNormalization()(upconv1)
		upconv1 = Activation('relu')(upconv1)
		
		final = Conv2D(2, (1, 1), strides=(1, 1), activation='linear', padding='same', init='he_normal')(upconv1)
		
		self.model = Model(input=inputs, output=final)
		self.model.load_weights('network/deepvel_weights.hdf5')
	
	def validation_generator(self):
		
		input_validation = np.zeros((self.batch_size, self.nx, self.ny, 2), dtype='float32')
		
		if(self.ic1_read_median == 0):
			self.ic1_median = np.median(self.observations[:, self.border_x1:self.border_x1+self.nx, self.border_y1:self.border_y1+self.ny])
		
		while 1:
			for i in range(self.n_frames):
				input_validation[:, :, :, 0] = self.observations[i*self.batch_size:(i + 1) * self.batch_size,
													self.border_x1:self.border_x1 + self.nx,
													self.border_y1:self.border_y1 + self.ny] / self.ic1_median
				input_validation[:, :, :, 1] = self.observations[i*self.batch_size + 1:(i + 1) * self.batch_size + 1,
													self.border_x1:self.border_x1 + self.nx,
													self.border_y1:self.border_y1 + self.ny] / self.ic1_median
				
				yield input_validation
		
		f.close()
	
	def predict(self):
		print("Predicting velocities with DeepVel...")
		
		start = time.time()
		out = self.model.predict_generator(self.validation_generator(), self.n_frames, max_q_size=1)
		end = time.time()
		
		print("Prediction took {0} seconds...".format(end - start))
		
		for i in range(6):
			out[:, :, :, i] = out[:, :, :, i] * (self.vv_max[i] - self.vv_min[i]) + self.vv_min[i]
		
		hdu = fits.PrimaryHDU(out)
		hdulist = fits.HDUList([hdu])
		hdulist.writeto(self.output, overwrite=True)


if (__name__ == '__main__'):
	parser = argparse.ArgumentParser(description='DeepVel prediction')
	parser.add_argument('-o', '--out', help='Output file')
	parser.add_argument('-i', '--in', help='Input file')
	parser.add_argument('-bx1', '--border_x1', help='Border size in pixels', default=0)
	parser.add_argument('-bx2', '--border_x2', help='Border size in pixels', default=0)
	parser.add_argument('-by1', '--border_y1', help='Border size in pixels', default=0)
	parser.add_argument('-by2', '--border_y2', help='Border size in pixels', default=0)
	parser.add_argument('-median', '--median', help='Read median value from file', default=0)
	parsed = vars(parser.parse_args())
	
	# Open file with observations and read them. We use FITS in our case
	f = fits.open(parsed['in'])
	imgs = f[0].data
	
	out = deepvel(imgs, parsed['out'],
								border_x1=int(parsed['border_x1']),
								border_x2=int(parsed['border_x2']),
								border_y1=int(parsed['border_y1']),
								border_y2=int(parsed['border_y2']),
								read_ic1_median=int(parsed['median']))
	out.define_network()
	out.predict()
