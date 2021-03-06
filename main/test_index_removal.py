from __future__ import print_function
from conv_qsar_fast.utils.parse_cfg import read_config
from conv_qsar_fast.utils.parsing import input_to_bool
from conv_qsar_fast.utils.neural_fp import sizeAttributeVector
import conv_qsar_fast.utils.reset_layers as reset_layers
import rdkit.Chem as Chem
import matplotlib.pyplot as plt
import datetime
import json
import sys
import os
import time
import numpy as np
from copy import deepcopy

from conv_qsar_fast.main.core import build_model
from conv_qsar_fast.main.test import test_model
from conv_qsar_fast.main.data import get_data_full

if __name__ == '__main__':
	if len(sys.argv) < 2:
		print('Usage: {} "settings.cfg"'.format(sys.argv[0]))
		quit(1)

	# Load settings
	try:
		config = read_config(sys.argv[1])
	except:
		print('Could not read config file {}'.format(sys.argv[1]))
		quit(1)

	# Get model label
	try:
		fpath = config['IO']['model_fpath']
	except KeyError:
		print('Must specify model_fpath in IO in config')
		quit(1)

	###################################################################################
	### LOAD STRUCTURE OR BUILD MODEL
	###################################################################################

	print('...building model')
	try:
		kwargs = config['ARCHITECTURE']
		del kwargs['__name__'] #  from configparser
		if 'batch_size' in config['TRAINING']:
			kwargs['padding'] = int(config['TRAINING']['batch_size']) > 1
		if 'embedding_size' in kwargs: 
			kwargs['embedding_size'] = int(kwargs['embedding_size'])
		if 'hidden' in kwargs: 
			kwargs['hidden'] = int(kwargs['hidden'])
		if 'depth' in kwargs: 
			kwargs['depth'] = int(kwargs['depth'])
		if 'scale_output' in kwargs: 
			kwargs['scale_output'] = float(kwargs['scale_output'])
		if 'dr1' in kwargs:
			kwargs['dr1'] = float(kwargs['dr1'])
		if 'dr2' in kwargs:
			kwargs['dr2'] = float(kwargs['dr2'])
		if 'output_size' in kwargs:
			kwargs['output_size'] = int(kwargs['output_size'])
		if 'sum_after' in kwargs:
			kwargs['sum_after'] = input_to_bool(kwargs['sum_after'])		
				
		model = build_model(**kwargs)
		print('...built untrained model')
	except KeyboardInterrupt:
		print('User cancelled model building')
		quit(1)

	###################################################################################
	### LOAD WEIGHTS?
	###################################################################################

	weights_fpath = fpath + '.h5'

	try:
		use_old_weights = input_to_bool(config['IO']['use_existing_weights'])
	except KeyError:
		print('Must specify whether or not to use existing model weights')
		quit(1)

	try:
		weights_fpath = config['IO']['weights_fpath']
	except KeyError:
		pass

	if use_old_weights and os.path.isfile(weights_fpath):
		# Load weights
		model.load_weights(weights_fpath)
		print('...loaded weight information')
	elif use_old_weights and not os.path.isfile(weights_fpath):
		print('Weights not found at specified path {}'.format(weights_fpath))
		quit(1)
	else:
		print('Could not load weights?')
		quit(1)
	
	###################################################################################
	### DEFINE DATA 
	###################################################################################

	data_kwargs = config['DATA']
	if '__name__' in data_kwargs:
		del data_kwargs['__name__'] #  from configparser
	if 'batch_size' in config['TRAINING']:
		data_kwargs['batch_size'] = int(config['TRAINING']['batch_size'])
	if 'shuffle_seed' in data_kwargs:
		data_kwargs['shuffle_seed'] = int(data_kwargs['shuffle_seed'])
	else:
		data_kwargs['shuffle_seed'] = int(time.time())
	if 'truncate_to' in data_kwargs:
		data_kwargs['truncate_to'] = int(data_kwargs['truncate_to'])
	if 'training_ratio' in data_kwargs:
		data_kwargs['training_ratio'] = float(data_kwargs['training_ratio'])
	if 'molecular_attributes' in data_kwargs: 
		data_kwargs['molecular_attributes'] = input_to_bool(data_kwargs['molecular_attributes'])
	else:
		raise ValueError('Need to use molecular attributes for this script')

	##############################
	### DEFINE TESTING CONDITIONS
	##############################

	conditions = [
		[],
		np.array([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]), # atom identity
		np.array([11, 12, 13, 14, 15, 16]), # number of heavy neighbors
		np.array([17, 18, 19, 20, 21]), # number of hydrogens
		np.array([22]), # formal charge
		np.array([23]), # in a ring
		np.array([24]), # is aromatic
		np.array([25]), # crippen contribution to logP
		np.array([26]), # crippen contribution to MR
		np.array([27]), # TPSA
		np.array([28]), # Labute ASA
		np.array([29]), # EState
		np.array([30]), # Gasteiger
		np.array([31]), # Gaasteiger hydrogen partial charge
		np.array([32, 33, 34, 35]), # Bond order
		np.array([36]), # Bond aromaticity
		np.array([37]), # Bond conjugation
		np.array([38]), # Bond in ring
	]

	# for i in range(1):#range(sizeAttributeVector() - 1):
	# 	conditions += [
	# 		np.array()
	# 	]

	for i, condition in enumerate(conditions):
		print('REMOVING: {}'.format(condition))

		# Get *FULL* dataset
		data_kwargs['training_ratio'] = 1.0
		data_kwargs['cv_folds'] = '1/1'
		data = get_data_full(**data_kwargs)

		average = None
		counter = 0.0
		# Calculate average value
		for i in range(3): # for each train, val, test
			for j in range(len(data[i]['mols'])): # for each mol in that list
				val = data[i]['mols'][j][:, :, condition]
				for k in range(val.shape[0]):
					if average is None:
						average = val[k, k, :]
					else:
						average = (average * counter + val[k, k, :]) / (counter + 1.0)
				counter += 1.0

		print('Condition: {}'.format(condition))
		print('Average: {}'.format(average))

		# Now filter as needed
		for i in range(3): # for each train, val, test
			for j in range(len(data[i]['mols'])): # for each mol in that list
				val = data[i]['mols'][j][:, :, condition] 
				for k in range(val.shape[0]):
					for l in range(val.shape[1]):
						if not (val[k, l, :] == 0.0).all():
							data[i]['mols'][j][k, l, condition] = average # reset that feature index to the avg

		###################################################################################
		### TEST MODEL
		###################################################################################
		if type(condition) != type([]):
			stamp = 'reset {}'.format(condition)
		else:
			stamp = 'baseline'
		print('...testing model')
		data_withresiduals = test_model(model, data, fpath, tstamp = stamp,
			batch_size = int(config['TRAINING']['batch_size']))
		print('...tested model')
