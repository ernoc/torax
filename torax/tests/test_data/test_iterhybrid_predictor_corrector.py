# Copyright 2024 DeepMind Technologies Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""ITER hybrid scenario based (roughly) on van Mulders NF 2021."""

import dataclasses
from torax import geometry
from torax import sim as sim_lib
from torax.config import runtime_params as general_runtime_params
from torax.sources import default_sources
from torax.sources import runtime_params as source_runtime_params
from torax.sources import source_models as source_models_lib
from torax.stepper import linear_theta_method
from torax.stepper import runtime_params as stepper_runtime_params
from torax.transport_model import qlknn_wrapper


def get_runtime_params() -> general_runtime_params.GeneralRuntimeParams:
  # NOTE: This approach to building the config is changing. Over time more
  # parts of this config will be built with pure Python constructors in
  # `get_sim()`.
  return general_runtime_params.GeneralRuntimeParams(
      plasma_composition=general_runtime_params.PlasmaComposition(
          # physical inputs
          Ai=2.5,  # amu of main ion (if multiple isotope, make average)
          Zeff=1.6,  # needed for qlknn and fusion power
          # effective impurity charge state assumed for matching dilution=0.862.
          Zimp=10,
      ),
      profile_conditions=general_runtime_params.ProfileConditions(
          Ip=10.5,  # total plasma current in MA
          # boundary + initial conditions for T and n
          Ti_bound_left=15,  # initial condition ion temperature for r=0
          Ti_bound_right=0.2,  # boundary condition ion temperature for r=Rmin
          Te_bound_left=15,  # initial condition electron temperature for r=0
          Te_bound_right=0.2,  # boundary condition electron temp for r=Rmin
          ne_bound_right=0.25,  # boundary condition density for r=Rmin
          # set initial condition density according to Greenwald fraction.
          nbar_is_fGW=True,
          nbar=0.8,
          npeak=1.5,  # Peaking factor of density profile
          # internal boundary condition (pedestal)
          # do not set internal boundary condition if this is False
          set_pedestal=True,
          Tiped=4.5,  # ion pedestal top temperature in keV for Ti and Te
          Teped=4.5,  # electron pedestal top temperature in keV for Ti and Te
          neped=0.62,  # pedestal top electron density in units of nref
          Ped_top=0.9,  # set ped top location in normalized radius
      ),
      numerics=general_runtime_params.Numerics(
          # simulation control
          t_final=5,  # length of simulation time in seconds
          # 1/multiplication factor for sigma (conductivity) to reduce current
          # diffusion timescale to be closer to heat diffusion timescale.
          resistivity_mult=200,
          ion_heat_eq=True,
          el_heat_eq=True,
          current_eq=True,
          dens_eq=True,
          maxdt=0.5,
          # multiplier in front of the base timestep dt=dx^2/(2*chi). Can likely
          # be increased further beyond this default.
          dtmult=50,
          dt_reduction_factor=3,
          # effective source to dominate PDE in internal boundary condtion
          # location if T != Tped
          largeValue_T=1.0e10,
          # effective source to dominate density PDE in internal boundary
          # condtion location if n != neped
          largeValue_n=1.0e8,
      ),
  )


def get_geometry(
    runtime_params: general_runtime_params.GeneralRuntimeParams,
) -> geometry.Geometry:
  return geometry.build_chease_geometry(
      runtime_params,
      geometry_file='ITER_hybrid_citrin_equil_cheasedata.mat2cols',
      Ip_from_parameters=True,
      Rmaj=6.2,  # major radius (R) in meters
      Rmin=2.0,  # minor radius (a) in meters
      B0=5.3,  # Toroidal magnetic field on axis [T]
  )


def get_transport_model() -> qlknn_wrapper.QLKNNTransportModel:
  return qlknn_wrapper.QLKNNTransportModel(
      runtime_params=qlknn_wrapper.RuntimeParams(
          DVeff=True,
          coll_mult=0.25,
          # set inner core transport coefficients (ad-hoc MHD/EM transport)
          apply_inner_patch=True,
          De_inner=0.25,
          Ve_inner=0.0,
          chii_inner=1.0,
          chie_inner=1.0,
          rho_inner=0.2,  # radius below which patch transport is applied
          # set outer core transport coefficients (L-mode near edge region)
          # For QLKNN model
          include_ITG=True,  # to toggle ITG modes on or off
          include_TEM=True,  # to toggle TEM modes on or off
          include_ETG=True,  # to toggle ETG modes on or off
          # ensure that smag - alpha > -0.2 always, to compensate for no slab
          # modes
          avoid_big_negative_s=True,
          # minimum |R/Lne| below which effective V is used instead of
          # effective D
          An_min=0.05,
          ITG_flux_ratio_correction=1,
          # allowed chi and diffusivity bounds
          chimin=0.05,  # minimum chi
          chimax=100,  # maximum chi (can be helpful for stability)
          Demin=0.05,  # minimum electron diffusivity
      ),
  )


def get_sources() -> source_models_lib.SourceModels:
  """Returns the source models used in the simulation."""
  source_models = default_sources.get_default_sources()
  # multiplier for ion-electron heat exchange term for sensitivity
  source_models.qei_source.runtime_params.Qei_mult = 1.0
  # Multiplication factor for bootstrap current (note fbs~0.3 in original simu)
  source_models.j_bootstrap.runtime_params.bootstrap_mult = 1.0
  source_models.jext.runtime_params = dataclasses.replace(
      source_models.jext.runtime_params,
      # total "external" current fraction
      fext=0.46,
      # width of "external" Gaussian current profile (normalized radial
      # coordinate)
      wext=0.075,
      # radius of "external" Gaussian current profile (normalized radial
      # coordinate)
      rext=0.36,
  )
  # pytype: disable=unexpected-keyword-arg
  # pylint: disable=unexpected-keyword-arg
  source_models.sources['generic_ion_el_heat_source'].runtime_params = (
      dataclasses.replace(
          source_models.sources['generic_ion_el_heat_source'].runtime_params,
          rsource=0.12741589640723575,
          # Gaussian width in normalized radial coordinate r
          w=0.07280908366127758,
          # total heating (including accounting for radiation) r
          Ptot=51.0e6,
          # electron heating fraction r
          el_heat_fraction=0.68,
      )
  )
  source_models.sources['gas_puff_source'].runtime_params = dataclasses.replace(
      source_models.sources['gas_puff_source'].runtime_params,
      # pellets behave like a gas puff for this simulation with exponential
      # decay therefore use the puff structure for pellets exponential decay
      # length of gas puff ionization (normalized radial coordinate)
      puff_decay_length=0.3,
      # total pellet particles/s
      S_puff_tot=6.0e21,
  )
  source_models.sources['pellet_source'].runtime_params = dataclasses.replace(
      source_models.sources['pellet_source'].runtime_params,
      # total pellet particles/s (continuous pellet model)
      S_pellet_tot=0.0e22,
      # Gaussian width of pellet deposition (normalized radial coordinate) in
      # continuous pellet model
      pellet_width=0.1,
      # Pellet source Gaussian central location (normalized radial coordinate)
      # in continuous pellet model.
      pellet_deposition_location=0.85,
  )
  source_models.sources['nbi_particle_source'].runtime_params = (
      dataclasses.replace(
          source_models.sources['nbi_particle_source'].runtime_params,
          # NBI total particle source
          S_nbi_tot=2.05e20,
          # NBI particle source Gaussian central location (normalized radial
          # coordinate)
          nbi_deposition_location=0.3,
          # NBI particle source Gaussian width (normalized radial coordinate)
          nbi_particle_width=0.25,
      )
  )
  # pytype: enable=unexpected-keyword-arg
  # pylint: enable=unexpected-keyword-arg
  source_models.sources['ohmic_heat_source'].runtime_params.mode = (
      source_runtime_params.Mode.ZERO
  )
  return source_models


def get_stepper_builder() -> linear_theta_method.LinearThetaMethodBuilder:
  """Returns a builder for the stepper that includes its runtime params."""
  builder = linear_theta_method.LinearThetaMethodBuilder(
      runtime_params=stepper_runtime_params.RuntimeParams(
          predictor_corrector=True,
          corrector_steps=1,
          # (deliberately) large heat conductivity for Pereverzev rule
          chi_per=30,
          # (deliberately) large particle diffusion for Pereverzev rule
          d_per=15,
          use_pereverzev=True,
      )
  )
  return builder


def get_sim() -> sim_lib.Sim:
  # This approach is currently lightweight because so many objects require
  # config for construction, but over time we expect to transition to most
  # config taking place via constructor args in this function.
  runtime_params = get_runtime_params()
  geo = get_geometry(runtime_params)
  return sim_lib.build_sim_from_config(
      runtime_params=runtime_params,
      geo=geo,
      stepper_builder=get_stepper_builder(),
      source_models=get_sources(),
      transport_model=get_transport_model(),
  )
