# MLMME
User behavior prediction in Pipedrive based on event logs

# Training:
Open terminal, locate the main.py directory and run `python main.py 'dataset location' 'training mode'`. The training mode can be 'mle' or 'mle-gan', where the former is the standard training and the latter is the adversarial training, but only 'mle-gan' is up to date to comply with Pipedrive event logs.

# Prediction:
After training, to get the best results for suffix prediction use 'rnnG(validation entropy gan).m', and for the remaining time prediction use 'rnnG(validation mae gan).m'.

