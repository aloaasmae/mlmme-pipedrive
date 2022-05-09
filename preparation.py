# -*- coding: utf-8 -*-


from __future__ import print_function, division

import datetime
import os
import sys
import time

import torch
import pandas as pd

from torch.utils.data import Dataset, DataLoader, TensorDataset
from tqdm import tqdm
import numpy as np

np.set_printoptions(linewidth=1000)
import pandas as pd
from torch.nn.utils.rnn import pad_sequence
import pickle
import pathlib
import collections


class Preprocessing:
    def __init__(self):
        self.batch_size = ''
        self.output_dir = ''
        self.dataset_name = ''
        self.input_path = ''
        self.data_augment = ''
        self.unique_event = ''  # List of events without <EOS>, i.e., [0]
        self.events = ''  # List of events with <EOS>, i.e., [0]
        self.weights_final = ''  # Weights assigned to each event
        self.desing_matrix = ''
        self.duration_time_max = ''  # Maximum duration time
        self.duration_time_min = ''  # minimum duration time (used for normalization)
        self.average_trace_length = ''
        self.std_trace_length = ''
        self.max_trace_length = ''
        self.activity_freq = ''  # Average and std frequency of an activity per trace. e.g., {6: [1.0003, 0.0163], 7: [1.5367, 0.8242],...}
        self.desing_matrix_partition_list = ''  # This is a list of lists, e.g. [ [[1,3,4],[2,3,1]], [[1,4,3,2,1]],.....] where traces of the same length are grouped (for computing speed up)
        self.prefix_from_begin_partition_list = ''
        self.suffix_to_end_partition_list = ''
        self.case_id_partition_list = ''
        self.duration_time_loc = ''
        self.selected_columns = ''  # A list shows the index of events and the duration time in the design matrix
        self.train_suffix_loader_partition_list = ''
        self.test_suffix_loader_partition_list = ''
        self.valid_suffix_loader_partition_list = ''
        self.separation_time = datetime.datetime.fromisoformat('2021-11-23T19:46:48.181')

    def read_input_csv(self):
        """

        @param input_path: Path to the CSV file
        @return:
        """
        dat = pd.read_csv(self.input_path)
        print("Types:", dat.dtypes)
        # changing the data type from integer to category
        dat['ActivityID'] = dat['ActivityID'].astype('category')
        dat['CompleteTimestamp'] = pd.to_datetime(dat['CompleteTimestamp'], dayfirst=True)
        print("Types after:", dat.dtypes)

        print("columns:", dat.columns)
        dat_group = dat.groupby('CaseID')
        print("Original data:", dat.head())
        print("Group by data:", dat_group.head())

        # Data Preparation
        # Iterating over groups in Pandas dataframe
        data_augment = pd.DataFrame()
        dat_group = dat.groupby('CaseID')
        for name, gr in dat_group:
            # sorting by time
            gr = gr.sort_values(['CompleteTimestamp'])
            duration_time = gr.loc[:, 'CompleteTimestamp'].diff() / np.timedelta64(1, 's')
            # Filling Nan with 0
            duration_time.iloc[0] = 0

            # computing the remaining time
            length = duration_time.shape[0]
            remaining_time = [np.sum(duration_time[i + 1:length]) for i in range(duration_time.shape[0])]

            gr['duration_time'] = duration_time
            gr['remaining_time'] = remaining_time

            data_augment = pd.concat([data_augment, gr])
            unique_event = sorted(data_augment['ActivityID'].unique())

        self.data_augment = data_augment
        self.unique_event = unique_event


        # return data_augment, unique_event

    ##############################################################################################
    def read_input_pickle(self):
        '''
        If you save the results of the above function ('read_input_csv') then you can load it to not run it for the second time.
        It is good to work with large datsest.
        @param input_path:
        @return:
        '''

        data_augment = pickle.load(open(self.input_path, "rb"))

        print(data_augment.shape)
        print(data_augment.head(50))

        # Creating a desing matrix (one hot vectors for activities), End of line (case) is denoted by class 0
        unique_event = sorted(data_augment['ActivityID'].unique())
        print("uniqe events:", unique_event)

        self.data_augment = data_augment
        self.unique_event = unique_event

        # return data_augment, unique_event

    ##############################################################################################
    def __event_to_one_hot(self):
        '''

        @param data_augment: The designed matrix, created from the input file (output of 'read_input_pickle()' or 'read_input_csv()')
        @return:
        '''

        l = []
        for index, row in tqdm(self.data_augment.iterrows()):
            temp = dict()
            '''
            temp ={1: 0,
                  2: 0,
                  3: 1,
                  4: 0,
                  5: 0,
                  6: 0,
                  '0':0,
                  'duration_time': 0.0,
                  'remaining_time': 1032744.0}
            '''

            # Defning the columns we consider
            keys = ['0'] + list(self.unique_event) + ['duration_time', 'remaining_time']
            for k in keys:
                if (k == row['ActivityID']):
                    temp[k] = 1
                else:
                    temp[k] = 0

            temp['class'] = row['ActivityID']
            temp['duration_time'] = row['duration_time']
            temp['remaining_time'] = row['remaining_time']
            temp['timestamp'] = row['CompleteTimestamp']
            temp['CaseID'] = row['CaseID']

            l.append(temp)

        # Creating a dataframe for dictionary l
        desing_matrix = pd.DataFrame(l)
        print("\n", desing_matrix.head(8))

        duration_time_min = desing_matrix['duration_time'].min()
        duration_time_max = desing_matrix['duration_time'].max()
        print("The maximum duration time is:", duration_time_max)
        desing_matrix['duration_time'] = (desing_matrix['duration_time'] - duration_time_min) / (
                duration_time_max - duration_time_min)

        self.desing_matrix = desing_matrix
        self.duration_time_max = duration_time_max
        self.duration_time_min = duration_time_min
        self.duration_time_loc = desing_matrix.columns.get_loc('duration_time')
        self.selected_columns = [0] + self.unique_event + [self.duration_time_loc]
        self.events = list(np.arange(0, len(self.unique_event) + 1))

    ##############################################################################################
    def __log_basic_stats(self):
        group = self.desing_matrix.groupby('CaseID')
        trace_length_list = [gr.shape[0] for name, gr in group]
        self.average_trace_length = np.mean(trace_length_list)
        self.std_trace_length = np.std(trace_length_list)
        self.max_trace_length = np.max(trace_length_list)
        print("The average length of traces:", np.mean(trace_length_list))
        print("The std of length of traces:", np.std(trace_length_list))
        print("The max of length of traces:", np.max(trace_length_list))

        # ---------------------------------------
        # Average frequency of each activity per trace
        activity_freq = dict.fromkeys(self.data_augment['ActivityID'].unique())

        group = self.data_augment.groupby(['CaseID'])

        for n, g in group:
            # print(g)
            freq = collections.Counter(g['ActivityID'])
            for k in freq.keys():
                if (k in activity_freq):
                    if (activity_freq[k] == None):
                        activity_freq[k] = [freq[k]]
                    else:
                        activity_freq[k].append(freq[k])

        for k in activity_freq:
            activity_freq[k] = [np.round(np.mean(activity_freq[k]), 4), np.round(np.std(activity_freq[k]), 4)]

        print('Activity frequencies:', activity_freq)
        self.activity_freq = activity_freq

    #############################################################################################
    def __log_partition(self, partition_width=2):
        '''
        Partitioning the log such that traces with similar sizes are in the same partition
        desing_matrix: A pandas data frame
        partition_width: The difference between the longest and shortest trace in a partition
        output: A list of desing matrices
        '''
        desing_matrix = self.desing_matrix

        group = desing_matrix.groupby(['CaseID'])
        trace_length_list = [gr.shape[0] for name, gr in group]
        max_trace_length = np.max(trace_length_list)
        min_trace_length = np.min(trace_length_list)

        no_partition = int(np.ceil((max_trace_length - min_trace_length) / partition_width))
        print("The number of partitions:", no_partition)

        # temp=[]
        desing_matrix_partition_list = []
        for i in range(no_partition):
            lower_ind = partition_width * i + min_trace_length
            upper_ind = partition_width * (i + 1) + min_trace_length

            case_id = []
            for n, g in group:
                if (g.shape[0] >= lower_ind and g.shape[0] < upper_ind):
                    case_id.append(n)
            if len(case_id) > 0:
                desing_matrix_partition_list.append(desing_matrix.loc[(desing_matrix['CaseID'].isin(case_id))])

        self.desing_matrix_partition_list = desing_matrix_partition_list


    ################################################################################################
    def __prefix_suffix_creating(self, prefix=2, mode="event_timestamp_prediction"):

        desing_matrix_partition_list = self.desing_matrix_partition_list
        prefix_from_begin_partition_list = []
        suffix_to_end_partition_list = []
        case_id_partition_list = []

        for desing_matrix in desing_matrix_partition_list:
            group = desing_matrix.groupby('CaseID')

            # Iterating over the groups to create tensors
            temp_prefix = []
            temp_suffix = []
            temp_case_id = []
            for name, gr in group:

                # For each group, i.e., view, we create a new dataframe and reset the index
                gr = gr.copy(deep=True)
                gr = gr.reset_index(drop=True)
                gr['timestamp'] = pd.to_datetime(gr['timestamp'])
                prefixes = gr[(gr['timestamp'] < self.separation_time)]
                if (prefixes.shape[0] == prefix and gr.shape[0] > prefixes.shape[0]):
                    # adding a new row at the bottom of each case to denote the end of a case
                    new_row = [0] * gr.shape[1]
                    gr.loc[gr.shape[0]] = new_row
                    gr.iloc[gr.shape[0] - 1, gr.columns.get_loc('0')] = 1  # End of line is denoted by class 0

                    gr_shift = gr.shift(periods=-1, fill_value=0)
                    gr_shift.loc[gr.shape[0] - 1, '0'] = 1

                    temp_case_id.append(name)

                    gr = gr.drop(['timestamp'], axis=1)
                    temp_prefix.append(
                        torch.tensor(gr.iloc[0:prefix].values, dtype=torch.float, requires_grad=False).cuda())
                    temp_suffix.append(
                        torch.tensor(gr.iloc[prefix:].values, dtype=torch.float, requires_grad=False).cuda())

            try:
                if len(temp_prefix) > 0 and len(temp_suffix) > 0:
                    # This part makes easier to work afterward
                    temp_prefix = pad_sequence(temp_prefix, batch_first=True, padding_value=0)
                    temp_suffix = pad_sequence(temp_suffix, batch_first=True, padding_value=0)
                    prefix_from_begin_partition_list.append(temp_prefix)
                    suffix_to_end_partition_list.append(temp_suffix)
                    case_id_partition_list.append(temp_case_id)

            except IndexError:
                pass

        self.prefix_from_begin_partition_list = prefix_from_begin_partition_list
        self.suffix_to_end_partition_list = suffix_to_end_partition_list
        self.case_id_partition_list = case_id_partition_list
        return prefix_from_begin_partition_list, suffix_to_end_partition_list, case_id_partition_list

    ###############################################################################################
    def __prefix_suffix_variable_length_creating(self):
        '''
        selexting (prefix,suffix) of variable length
        '''
        max_trace_length = self.max_trace_length

        prefix_suffix_dic = {}
        for i in range(2, int(max_trace_length)):
            print("prefix,suffix:", i)
            # Creating prefix and suffix of different length
            prefix_from_begin_partition_list, suffix_to_end_partition_list, case_id_partition_list = self.__prefix_suffix_creating(
                prefix=i, mode="event_prediction")

            prefix_suffix_dic[i] = (
                prefix_from_begin_partition_list, suffix_to_end_partition_list, case_id_partition_list)

        pr_all = []
        sf_all = []
        id_all = []
        for k in prefix_suffix_dic.keys():
            pr_all += prefix_suffix_dic[k][0]
            sf_all += prefix_suffix_dic[k][1]
            id_all += prefix_suffix_dic[k][2]

        out = os.path.join(self.output_dir, 'prefix_suffix_' + self.dataset_name + '.pkl')
        pickle.dump((pr_all, sf_all, id_all), open(out, "wb"))

        self.prefix_from_begin_partition_list = pr_all
        self.suffix_to_end_partition_list = sf_all
        self.case_id_partition_list = id_all

    ##################################################################################################
    def __pad_correction(self):
        suffix_to_end_partition_list = self.suffix_to_end_partition_list

        for j in range(len(suffix_to_end_partition_list)):
            for i in range(suffix_to_end_partition_list[j].size()[0]):
                u = (suffix_to_end_partition_list[j][i, :, 0] == 1).nonzero()

                try:
                    suffix_to_end_partition_list[j][i, :, 0][u:] = 1
                except TypeError:
                    pass

        self.suffix_to_end_partition_list = suffix_to_end_partition_list

    ##################################################################################################
    def __train_valid_test_loader(self, batch=4):
        '''
        Creating train,test, and validation loaders
        '''
        prefix_from_begin_partition_list = self.prefix_from_begin_partition_list
        suffix_to_end_partition_list = self.suffix_to_end_partition_list
        case_id_partition_list = self.case_id_partition_list

        train_suffix_loader_partition_list = []
        test_suffix_loader_partition_list = []
        valid_suffix_loader_partition_list = []

        # Iterating over the list of prefixes and suffixes
        for i in range(len(prefix_from_begin_partition_list)):
            prefix_from_begin = prefix_from_begin_partition_list[i]
            suffix_to_end = suffix_to_end_partition_list[i]
            case_id = torch.tensor(case_id_partition_list[i])

            train_inds_suffix = np.arange(0, round(prefix_from_begin.size()[0] * .7))
            validation_inds_suffix = np.arange(round(prefix_from_begin.size()[0] * .7),
                                               round(prefix_from_begin.size()[0] * .8))
            test_inds_suffix = np.arange(round(prefix_from_begin.size()[0] * .8), round(prefix_from_begin.size()[0]))

            # In a rare cases when the number of traning is less than 5
            if (len(test_inds_suffix) == 0 or len(validation_inds_suffix) == 0):
                test_inds_suffix = train_inds_suffix
                validation_inds_suffix = train_inds_suffix
                # continue

            train_suffix_data = TensorDataset(prefix_from_begin[train_inds_suffix], suffix_to_end[train_inds_suffix],
                                              case_id[train_inds_suffix])
            train_suffix_loader = DataLoader(dataset=train_suffix_data, batch_size=batch, shuffle=False)

            test_suffix_data = TensorDataset(prefix_from_begin[test_inds_suffix], suffix_to_end[test_inds_suffix],
                                             case_id[test_inds_suffix])
            test_suffix_loader = DataLoader(dataset=test_suffix_data, batch_size=batch, shuffle=False)

            validation_suffix_data = TensorDataset(prefix_from_begin[validation_inds_suffix],
                                                   suffix_to_end[validation_inds_suffix],
                                                   case_id[validation_inds_suffix])
            validation_suffix_loader = DataLoader(dataset=validation_suffix_data, batch_size=batch, shuffle=False)

            train_suffix_loader_partition_list.append(train_suffix_loader)
            test_suffix_loader_partition_list.append(test_suffix_loader)
            valid_suffix_loader_partition_list.append(validation_suffix_loader)

            self.train_suffix_loader_partition_list = train_suffix_loader_partition_list
            self.test_suffix_loader_partition_list = test_suffix_loader_partition_list
            self.valid_suffix_loader_partition_list = valid_suffix_loader_partition_list

    ##################################################################################################
    def __weight_of_event(self):
        '''
        This module assigns weights to events
        '''
        weights_final = []
        for i in range(len(self.events)):
            if i == 0:
                weights_final.append(1)
            else:
                weights_final.append(1)

        self.weights_final = torch.tensor(weights_final).float().cuda()




    def save(self):
        out = open(os.path.join(os.getcwd(), 'data', self.dataset_name + '.pkl'), "wb")
        pickle.dump(self.__dict__,  out, 2)
        out.close()

    def run(self, input_path, batch_size=128):
        self.batch_size = batch_size
        # Creating directory to save results
        if ('/' in input_path):  # For linux
            splt_char = '/'
        elif ('\\' in input_path):  # For windows
            splt_char = '\\'
        self.dataset_name = input_path.split(splt_char)[-1].split('.')[-2]
        folder_name = self.dataset_name +"_"+ time.strftime("%Y%m%d-%H%M%S")
        self.output_dir = os.path.join(os.getcwd(), 'results', folder_name)
        if not os.path.isdir(os.path.join(os.getcwd(), 'results', folder_name)):
            pathlib.Path(self.output_dir).mkdir(parents=True, exist_ok=True)

        self.input_path = input_path
        if (input_path.split('.')[-1] == 'csv'):
            self.read_input_csv()
            # Creating one hot representation
            self.__event_to_one_hot()
            self.__log_basic_stats()
            self.__log_partition()
            self.__prefix_suffix_variable_length_creating()
            self.save()
        elif (input_path.split('.')[-1] == 'pkl'):
            self.read_input_pickle()
            # Creating one hot representation
            self.__event_to_one_hot()
            self.__log_basic_stats()
            self.__log_partition()
            self.__prefix_suffix_variable_length_creating()
        # -----------
        self.__pad_correction()
        self.__weight_of_event()
        self.__train_valid_test_loader(batch=self.batch_size)
