import time
import ray
from ray import tune
import json
from hyperspace import create_hyperspace
from ray.tune.suggest.skopt import SkOptSearch
from skopt import Optimizer
from tqdm import tqdm
import sys
import pandas as pd
import os
import pickle
from ray.tune.logger import DEFAULT_LOGGERS
from ray.tune.integration.wandb import WandbLoggerCallback
from ray.tune.suggest import ConcurrencyLimiter
import torch
import traceback


NUM_GPUS=None
NUM_CPUS=None

def get_trials(json_file):
    # load hyperspace boundaries from json file
    try:
        f = open(json_file, "r")
    except Exception as e:
        print(e)
        print("ERROR: json file with hyperparameter bounds not found. Please use utils.create_json() function "
              "to generate boundary file and try again.")
        sys.exit()
    bounds = json.load(f)
    for n in bounds:
        bounds[n] = tuple(bounds[n])
    hyperparameters = list(bounds.values())
    space = create_hyperspace(hyperparameters)
    return space, bounds

@ray.remote(num_gpus=NUM_GPUS, max_calls=1, num_cpus=NUM_CPUS)
def run_specific_spaces(spaces, bounds, intermediate_dir, func, trials, mode, metric,
                        ray_dir, project_name, group_name,
                        wandb_key, trial_name_creator, extra_data_dir):

    """Given a chunk of spaces, run sequentially on ray tune. Spaces are given as pair, with 0th being space num"""
    global NUM_CPUS, NUM_GPUS
    for i, value in spaces:
        # Using 10 initial points before beginning GP optimization, same as original Hyperspace implementation
        # https://github.com/maxzvyagin/hyperspace/blob/f772f314a2fdbe7361e469e9002d501a542085bc/hyperspace/hyperdrive/skopt/hyperdrive.py#L108
        optimizer = Optimizer(value, random_state=0, n_initial_points=10)
        search_algo = SkOptSearch(optimizer, list(bounds.keys()), metric=metric, mode=mode)
        search_algo = ConcurrencyLimiter(search_algo, max_concurrent=1)
        try:
            if wandb_key != "insert_your_key_here":
                callbacks = [WandbLoggerCallback(
                    project=project_name, group=group_name,
                    api_key=wandb_key,
                    log_config=True)]
                config_dict = {"wandb": {
                                    "project": project_name,
                                    "api_key": wandb_key}}
            else:
                callbacks = None
                config_dict = None
            analysis = tune.run(tune.with_parameters(func, extra_data_dir=extra_data_dir), search_alg=search_algo,
                                num_samples=trials,
                                resources_per_trial={'cpu': NUM_CPUS, 'gpu': NUM_GPUS}, trial_name_creator=trial_name_creator,
                                local_dir=ray_dir, callbacks=callbacks,
                                config=config_dict)

            df = analysis.results_df
            df.to_csv(intermediate_dir + "/space" + str(i) + ".csv")
            opt_result = optimizer.get_result()
            f = open(intermediate_dir + "/optimizer_result" + str(i) + ".pkl", "wb+")
            pickle.dump(opt_result, f)
        except Exception as e:
            print(traceback.format_exc())
            print(e)
            print("Failure to run space {}, contintuing with next spaces.".format(i))
    return 0


def get_chunks(l, n):
    ### from https://gist.github.com/joyrexus/5571989
    size = len(l) / float(n)
    I = lambda i: int(round(i))
    return [l[I(size * i):I(size * (i + 1))] for i in range(n)]

def run_experiment(func, json_file, num_trials, out_directory, mode="max", metric="average_res",
                          ray_dir="/tmp/ray_results/", cpu=8, gpu=1, start_space=None,
                   project_name='default_project', group_name='default_group', wandb_key='insert_your_key_here',
                trial_name_creator=None, extra_data_dir={}, num_splits=None):

    """ Generate hyperparameter spaces and run each space sequentially. """
    start_time = time.time()
    try:
        ray.init(address='auto', include_dashboard=False)
    except:
        try:
            ray.init()
            print("Started ray without auto address.")
        except:
            print("Ray.init failed twice.")
        print("WARNING: could not connect to existing Ray Cluster. Ignore warning if only running on single node.")
    # print(ray.cluster_resources())
    try:
        os.mkdir(out_directory)
        print("Created directory to save intermediate results at " + out_directory)
    except:
        print("WARNING: Could not create directory for intermediate results. Check that the directory does not already"
              "exist - files will be overwritten. Intermediate directory is " + out_directory)

    global NUM_CPUS, NUM_GPUS
    NUM_CPUS = cpu
    NUM_GPUS = gpu

    space, bounds = get_trials(json_file)
    space = list(zip(list(range(len(space))), space))
    if start_space:
        space = space[start_space:]
    n = 1
    # generate space splits
    if num_splits:
        n = num_splits
    else:
        try:
            num_cluster_gpus = ray.cluster_resources()['GPU']
            if num_cluster_gpus > 0:
                n = num_cluster_gpu
        except Exception as e:
            if torch.cuda.device_count() > 0:
                n = torch.cuda.device_count()
        else:
            n = 1
            print("NOTE: No GPUs found and num_splits not provided as argument. Defaulting to single split.")
    space_splits = get_chunks(space, n)

    futures = [run_specific_spaces.remote(s, bounds=bounds, func=func, intermediate_dir=out_directory,
                                          trials=int(num_trials), mode=mode, metric=metric,
                                          ray_dir=ray_dir, project_name=project_name, group_name=group_name,
                                          wandb_key=wandb_key, trial_name_creator=trial_name_creator,
                                          extra_data_dir=extra_data_dir) for s in space_splits]

    print(ray.get(futures))

    print("Measured time needed to run trials: ")
    execution_time = (time.time() - start_time)
    print('Execution time in seconds: ' + str(execution_time))
