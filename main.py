import preparation as pr
import network as nw
import suffix as sf
import torch
from torchviz import make_dot
import os
import sys
import pickle


def main(input_path, training_mode='mle-gan'):
    # Preprocessing data
    if input_path.split('.')[-1] == 'pkl':
        data_obj = load(input_path)
    else:
        data_obj = pr.Preprocessing()
        data_obj.training_mode = training_mode
        data_obj.run(input_path)

        out = open((input_path[:-3] + 'pkl'), "wb")
        pickle.dump(data_obj, out)
        out.close()

    # Creating network object
    # Parameters
    input_size = len(data_obj.selected_columns)
    batch = data_obj.batch_size
    hidden_size = 200
    num_layers = 5
    num_directions = 1  # It should be 2 if we use bidirectional
    beam_width = [i for i in range (2, 21, 2)]  # Window size of beam search

    # Creating Networks
    enc = nw.Encoder(input_size, batch, hidden_size, num_layers, num_directions).cuda()
    dec = nw.Decoder(input_size, batch, hidden_size, num_layers, dropout=.3).cuda()
    dec.duration_time_loc = data_obj.duration_time_loc
    rnnD = nw.Discriminator(input_size, batch, hidden_size, num_layers, dropout=.3).cuda()
    model = nw.Seq2Seq(enc, dec).cuda()
    # Initializing model parameters
    model.apply(nw.init_weights)
    rnnD.apply(nw.init_weights)
    # Creating optimizers
    optimizerG = torch.optim.RMSprop(model.parameters(), lr=5e-5)
    optimizerD = torch.optim.RMSprop(rnnD.parameters(), lr=5e-5)
    make_dot(model, params=dict(model.named_parameters()))
    if training_mode == 'mle':
        print("Training via MLE")
        nw.train_mle(model, optimizerG, data_obj)
        # Loading the best model saved during training
        path = os.path.join(data_obj.output_dir, 'rnnG(validation entropy).m')
        model.load_state_dict(torch.load(path))
        nw.model_eval_test(model, data_obj, mode='test')

    elif training_mode == 'mle-gan':
        print("Training via MLE-GAN")
        # Training via MLE-GAN
        try:
            nw.train_gan(model, rnnD, optimizerG, optimizerD, data_obj)
        except Exception as e:
            print(e)
        finally:
            # Loading the best model saved during training
            path = os.path.join(data_obj.output_dir, 'rnnG(validation entropy gan).m')
            model.load_state_dict(torch.load(path))
            nw.model_eval_test(model, data_obj, mode='test')
    # -------------------------------------------
    elif (training_mode == 'test'):
        print("Testing...")
        # Training via MLE-GAN
        # Loading the best model saved during training
        path = os.path.join("test", 'rnnG(validation entropy gan).m')
        model.load_state_dict(torch.load(path))
        nw.model_eval_test(model, data_obj, mode='test')
    # Generating suffixes
    print("start generating suffixes using beam search!")
    for i in beam_width:
        sf.suffix_generate(model, data_obj, candidate_num=i)
        sf.suffix_similarity(data_obj, beam_size=i)

    return data_obj, model


def load(out):

    f = open(out, 'rb')
    data_obj = pickle.load(f)
    f.close()

    return data_obj

if __name__ == "__main__":


    print(sys.argv)
    log_name = sys.argv[1]
    training_mode = sys.argv[2]
    input_path = os.path.join(os.getcwd(), 'data', log_name)

    print("Input data:", input_path)
    print("Training mode:", training_mode)

    main(input_path, training_mode)

