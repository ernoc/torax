# What is TORAX?

TORAX is a differentiable tokamak core transport simulator aimed for fast and accurate forward modelling, pulse-design, trajectory optimization, and controller design workflows. TORAX is written in Python-JAX, with the following motivations:

- Open-source and extensible, aiding with flexible workflow coupling
- JAX provides auto-differentiation capabilities and code compilation for fast runtimes. Differentiability allows for gradient-based nonlinear PDE solvers for fast and accurate modelling, and for sensitivity analysis of simulation results to arbitrary parameter inputs, enabling applications such as trajectory optimization and data-driven parameter identification for semi-empirical models. Auto-differentiability allows for these applications to be easily extended with the addition of new physics models, or new parameter inputs, by avoiding the need to hand-derive Jacobians
- Python-JAX is a natural framework for the coupling of ML-surrogates of physics models

TORAX is in a pre-beta phase with a basic physics feature set, including:

- Coupled PDEs of ion and electron heat transport, electron particle transport, and current diffusion
    - Finite-volume-method
    - Multiple solver options: linear with Pereverzev-Corrigan terms, nonlinear with Newton-Raphson, nonlinear with optimization using the jaxopt library
- Ohmic power, ion-electron heat exchange, fusion power, bootstrap current with the analytical Sauter model
- Time dependent boundary conditions and sources
- Coupling to the QLKNN10D [[van de Plassche et al, Phys. Plasmas 2020]](https://doi.org/10.1063/1.5134126) QuaLiKiz-neural-network surrogate for physics-based turbulent transport
- General geometry, provided via CHEASE equilibrium files
    - For testing and demonstration purposes, a single CHEASE equilibrium file is available in the data/geo directory. It corresponds to an ITER hybrid scenario equilibrium based on simulations in [[Citrin et al, Nucl. Fusion 2010]](https://doi.org/10.1088/0029-5515/50/11/115007), and was obtained from [PINT](https://gitlab.com/qualikiz-group/pyntegrated_model). A PINT license file is available in data/geo.

Additional heating and current drive sources can be provided by prescribed formulas, or user-provided analytical models.

Model implementation was verified through direct comparison of simulation outputs to the RAPTOR [[Felici et al, Plasma Phys. Control. Fusion 2012]](https://iopscience.iop.org/article/10.1088/0741-3335/54/2/025002) tokamak transport simulator.

This is not an officially supported Google product.

## Feature roadmap

Short term development plans include:

- Time dependent geometry
- Time dependent prescribed state profiles
- More flexible initial conditions
- Implementation of forward sensitivity calculations w.r.t. control inputs and parameters
- Implementation of persistent compilation cache for CPU
- Performance optimization and cleanup
- More extensive documentation and tutorials
- Visualisation: run summaries, run comparisons
- Port the unit-test and integration test suite

Longer term desired features include:

- Sawtooth model (Porcelli + reconnection)
- Neoclassical tearing modes (modified Rutherford equation)
- Radiation sinks
    - Cyclotron radiation
    - Bremsstrahlung
    - Line radiation
- Neoclassical transport + multi-ion transport, with a focus on heavy impurities
- IMAS coupling
- Stationary-state solver
- Momentum transport

Contributions in line with the roadmap are welcome. In particular, TORAX is envisaged as a natural framework for coupling of various ML-surrogates of physics models. These could include surrogates for turbulent transport, neoclassical transport, heat and particle sources, line radiation, pedestal physics, and core-edge integration, MHD, among others.

# Installation guide

## Requirements

Install Python 3.10 or greater.

Make sure that tkinter is installed:

```shell
sudo apt-get install python3-tk
```

## How to install

Install virtualenv (if not already installed):

```shell
pip install --upgrade pip
```

```shell
pip install virtualenv
```

Create a code directory where you will install the virtual env and other TORAX
dependencies.

```shell
mkdir /path/to/torax_dir && cd "$_"
```
Where `/path/to/torax_dir` should be replaced by a path of your choice.

Create a TORAX virtual env:

```shell
python3 -m venv toraxvenv
```

Activate the virtual env:

```shell
source toraxvenv/bin/activate
```

Download QLKNN dependencies:

```shell
git clone https://gitlab.com/qualikiz-group/qlknn-hyper.git
```

```shell
export TORAX_QLKNN_MODEL_PATH="$PWD"/qlknn-hyper
```

It is recommended to automate the environment variable export. For example, if using bash, run:

```shell
echo export TORAX_QLKNN_MODEL_PATH="$PWD"/qlknn-hyper >> ~/.bashrc
```
The above command only needs to be run once on a given system.

Download and install the TORAX codebase via http:

```shell
git clone https://github.com/google-deepmind/torax.git
```
or ssh (ensure that you have the appropriate SSH key uploaded to github).

```shell
git clone git@github.com:google-deepmind/torax.git
```
Enter the TORAX directory and pip install the dependencies.

```shell
cd torax; pip install .
```

Optional: Install additional GPU support for JAX if your machine has a GPU:
https://jax.readthedocs.io/en/latest/installation.html#supported-platforms

## Running an example

The following command will run TORAX using the configuration file `tests/test_data/default_config.py`. TORAX configuration files overwrite the defaults in `config.py`. Comments in `config.py` provide a brief explanation of all configuration variables. More detailed documentation is on the roadmap.

```shell
python3 run_simulation_main.py \
   --python_config='torax.tests.test_data.default_config --log_progress'
```

Additional configuration is provided through flags which append the above run command, and environment variables:

### Set environment variables

Path to the QuaLiKiz-neural-network parameters. Note: if installation instructions above were followed, this may already be set.

```shell
$ export TORAX_QLKNN_MODEL_PATH="<myqlknnmodelpath>"
```

Path to the geometry file directory. This prefixes the path and filename provided in the `geometry_file` geometry constructor argument in the run config file. If not set, `TORAX_GEOMETRY_DIR` defaults to the relative path `torax/data/third_party/geo`.

```shell
$ export TORAX_GEOMETRY_DIR="<mygeodir>"
```

If true, error checking is enabled in internal routines. Used for debugging. Default is false since it is incompatible with the persistent compilation cache.

```shell
$ export TORAX_ERRORS_ENABLED=<True/False>
```

If false, JAX does not compile internal TORAX functions. Used for debugging. Default is true.

```shell
$ export TORAX_COMPILATION_ENABLED=<True/False>
```


### Set flags
Output simulation time, dt, and number of stepper iterations (dt backtracking with nonlinear solver) carried out at each timestep.

```shell
python3 run_simulation_main.py \
   --python_config='torax.tests.test_data.default_config' \
   --log_progress
```

Live plotting of simulation state and derived quantities.

```shell
python3 run_simulation_main.py \
   --python_config='torax.tests.test_data.default_config' \
   --plot_progress
```

Combination of the above.

```shell
python3 run_simulation_main.py \
   --python_config='torax.tests.test_data.default_config' \
   --log_progress --plot_progress
```

### Post-simulation

Once complete, the time history of a simulation state and derived quantities is written to `state_history.h5`. The output path is written to stdout

To take advantage of the in-memory (non-persistent) cache, the process does not end upon simulation termination. It is possible to modify the config, toggle the `log_progress` and `plot_progress` flags, and rerun the simulation. Only the following modifications will then trigger a recompilation:

- Grid resolution
- Evolved variables (equations being solved)
- Changing internal functions used, e.g. transport model, or time_step_calculator


## Cleaning up

You can get out of the Python virtual env by deactivating it:

```shell
deactivate
```

# Simulation tutorials

Under construction

# FAQ

* On MacOS, you may get the error: .. ERROR:: Could not find a local HDF5
  installation.:
* Solution: You need to tell the OS where HDF5 is, try

```shell
brew install hdf5
```

```shell
export HDF5_DIR="$(brew --prefix hdf5)"
```

```shell
pip install --no-binary=h5py h5py
```