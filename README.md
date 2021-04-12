# SpaceRay
Integration of HyperSpace with Ray Tune hyperparameter search functionality. Requires definition of objective function, number of trials, and hyperparameter bounds in JSON format. Also, if you plan on using the Weight and Biases functionality with logging in your objective function, you must specify your own Weight and Biases API Key. Logging should be performed using the `@wandb.mixin` decorator from Ray Tune.
More information on that can be found here: https://docs.ray.io/en/master/tune/tutorials/tune-wandb.html

Note that this processes that generated hyperspaces concurrently, meaning that end results will need to be manually concatenated or processed individually in the specified results directory. 

For more information on the HyperSpace library, see the original repo: https://github.com/yngtodd/hyperspace. __HyperSpace must be installed in order for SpaceRay to work properly.__

_In addition, HyperSpace requires these two specific `scikit` versions to work properly_:
- `scikit-optimize==0.5.2`
- `scikit-learn==`

To install SpaceRay, simply clone and run `pip install .` within the top level directory.

To see an example of how to use the tuning function, check out the `example` folder.