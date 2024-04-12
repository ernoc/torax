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

"""Tests checking the output core_sources profiles from run_simulation().

This is a separate file to not bloat the main sim.py test file.
"""

import dataclasses
from typing import Any

from absl.testing import absltest
from jax import numpy as jnp
import numpy as np
from torax import config as config_lib
from torax import config_slice
from torax import geometry
from torax import initial_states
from torax import sim as sim_lib
from torax import state as state_module
from torax.fvm import cell_variable
from torax.sources import source
from torax.sources import source_config
from torax.sources import source_models as source_models_lib
from torax.sources import source_profiles as source_profiles_lib
from torax.tests.test_lib import explicit_stepper
from torax.tests.test_lib import sim_test_case
from torax.time_step_calculator import time_step_calculator as ts
from torax.transport_model import constant as constant_transport_model


_ALL_PROFILES = ('temp_ion', 'temp_el', 'psi', 'q_face', 's_face', 'ne')


class SimOutputSourceProfilesTest(sim_test_case.SimTestCase):
  """Tests checking the output core_sources profiles from run_simulation()."""

  def test_merging_source_profiles(self):
    """Tests that the implicit and explicit source profiles merge correctly."""
    config = config_lib.Config()
    geo = geometry.build_circular_geometry(config)
    dynamic_config_slice = config_slice.build_dynamic_config_slice(config)
    static_config_slice = config_slice.build_static_config_slice(config)
    source_models = source_models_lib.SourceModels()
    # Technically, the _merge_source_profiles() function should be called with
    # source profiles where, for every source, only one of the implicit or
    # explicit profiles has non-zero values. That is what makes the summing
    # correct. For this test though, we are simply checking that things are
    # summed in the first place.
    # Build a fake set of source profiles which have all 1s in all the profiles.
    fake_implicit_source_profiles = _build_source_profiles_with_single_value(
        dynamic_config_slice=dynamic_config_slice,
        geo=geo,
        source_models=source_models,
        value=1.0,
    )
    # And a fake set of profiles with all 2s.
    fake_explicit_source_profiles = _build_source_profiles_with_single_value(
        dynamic_config_slice=dynamic_config_slice,
        geo=geo,
        source_models=source_models,
        value=2.0,
    )
    qei_core_profiles = initial_states.initial_core_profiles(
        dynamic_config_slice=dynamic_config_slice,
        static_config_slice=static_config_slice,
        geo=geo,
        source_models=source_models,
    )
    qei_core_profiles = dataclasses.replace(
        qei_core_profiles,
        temp_ion=cell_variable.CellVariable(
            value=jnp.ones_like(geo.r) * 1.0,
            dr=geo.dr,
        ),
        temp_el=cell_variable.CellVariable(
            value=jnp.ones_like(geo.r) * 3.0,
            dr=geo.dr,
        ),
    )
    merged_profiles = sim_lib._merge_source_profiles(  # pylint: disable=protected-access
        source_models=source_models,
        implicit_source_profiles=fake_implicit_source_profiles,
        explicit_source_profiles=fake_explicit_source_profiles,
        qei_core_profiles=qei_core_profiles,
    )
    # All the profiles in the merged profiles should be a 1D array with all 3s.
    # Except the Qei profile, which is a special case.
    for name, profile in merged_profiles.profiles.items():
      if name != source_models.qei_source.name:
        np.testing.assert_allclose(profile, 3.0)
      else:
        np.testing.assert_allclose(profile, 6.0)
    # Make sure the combo ion-el heat sources were split up.
    for name in ['generic_ion_el_heat_source', 'fusion_heat_source']:
      self.assertNotIn(name, merged_profiles.profiles)
      self.assertIn(f'{name}_ion', merged_profiles.profiles)
      self.assertIn(f'{name}_el', merged_profiles.profiles)

  def test_first_and_last_source_profiles(self):
    """Tests that the first and last source profiles contain correct data."""
    # The first time step and last time step's output source profiles are built
    # in a special way that combines the implicit and explicit profiles.

    # Create custom sources which output profiles depending on the pellet_width.
    def custom_source_formula(dynamic_config, geo, unused_state):
      # Combine the outputs of the pellet
      return jnp.ones_like(geo.r) * dynamic_config.pellet_width

    # Include 2 versions of this source, one implicit and one explicit.
    source_models = source_models_lib.SourceModels(
        additional_sources=[
            source.SingleProfileSource(
                name='implicit_ne_source',
                supported_types=(
                    source_config.SourceType.ZERO,
                    source_config.SourceType.FORMULA_BASED,
                ),
                affected_core_profiles=(source.AffectedCoreProfile.NE,),
                formula=custom_source_formula,
            ),
            source.SingleProfileSource(
                name='explicit_ne_source',
                supported_types=(
                    source_config.SourceType.ZERO,
                    source_config.SourceType.FORMULA_BASED,
                ),
                affected_core_profiles=(source.AffectedCoreProfile.NE,),
                formula=custom_source_formula,
            ),
        ]
    )
    # Linearly scale the pellet_width.
    config = config_lib.Config(
        pellet_width={0.0: 1.0, 1.0: 2.0, 2.0: 3.0, 3.0: 4.0},
        sources={
            'implicit_ne_source': source_config.SourceConfig(
                source_type=source_config.SourceType.FORMULA_BASED,
                is_explicit=False,
            ),
            'explicit_ne_source': source_config.SourceConfig(
                source_type=source_config.SourceType.FORMULA_BASED,
                is_explicit=True,
            ),
        },
    )
    geo = geometry.build_circular_geometry(config)
    time_stepper = _FakeTimeStepCalculator()
    step_fn = _FakeSimulationStepFn(time_stepper, source_models)
    dynamic_config_slice_provider = (
        config_slice.TimeDependentDynamicConfigSliceProvider(config)
    )
    initial_dcs = dynamic_config_slice_provider(0.0)
    static_config_slice = config_slice.build_static_config_slice(config)

    sim_states = sim_lib.run_simulation(
        initial_state=sim_lib.get_initial_state(
            dynamic_config_slice=initial_dcs,
            static_config_slice=static_config_slice,
            geo=geo,
            time_step_calculator=time_stepper,
            source_models=source_models,
        ),
        step_fn=step_fn,
        geometry_provider=sim_lib.ConstantGeometryProvider(geo),
        dynamic_config_slice_provider=dynamic_config_slice_provider,
        static_config_slice=static_config_slice,
        time_step_calculator=time_stepper,
    )

    # The implicit and explicit profiles get merged together before being
    # outputted, and they are aligned as well as possible to be computed based
    # on the state and config at time t. So both the implicit and explicit
    # profiles of each time step should be equal in this case (especially
    # because we are using the fake step function defined below).
    for i, sim_state in enumerate(sim_states):
      np.testing.assert_allclose(
          sim_state.core_sources.profiles['implicit_ne_source'], i + 1
      )
      np.testing.assert_allclose(
          sim_state.core_sources.profiles['explicit_ne_source'], i + 1
      )


def _build_source_profiles_with_single_value(
    dynamic_config_slice: config_slice.DynamicConfigSlice,
    geo: geometry.Geometry,
    source_models: source_models_lib.SourceModels,
    value: float,
):
  cell_1d_arr = jnp.ones_like(geo.r) * value
  face_1d_arr = jnp.ones_like(geo.r_face) * value
  return source_profiles_lib.SourceProfiles(
      profiles={
          name: (
              jnp.ones(
                  shape=src.output_shape_getter(dynamic_config_slice, geo, None)
              )
              * value
          )
          for name, src in source_models.standard_sources.items()
      },
      j_bootstrap=source_profiles_lib.BootstrapCurrentProfile(
          sigma=cell_1d_arr * value,
          j_bootstrap=cell_1d_arr * value,
          j_bootstrap_face=face_1d_arr * value,
          I_bootstrap=jnp.ones(()) * value,
      ),
      qei=source_profiles_lib.QeiInfo(
          qei_coef=cell_1d_arr,
          implicit_ii=cell_1d_arr,
          explicit_i=cell_1d_arr,
          implicit_ee=cell_1d_arr,
          explicit_e=cell_1d_arr,
          implicit_ie=cell_1d_arr,
          implicit_ei=cell_1d_arr,
      ),
  )


class _FakeTimeStepCalculator(ts.TimeStepCalculator):
  """Fake time step calculator which only runs the sim for 2 seconds."""

  def initial_state(self):
    return ()

  def not_done(
      self,
      t: float | jnp.ndarray,
      dynamic_config_slice: config_slice.DynamicConfigSlice,
      state,
  ) -> bool | jnp.ndarray:
    return t < 2

  def next_dt(
      self,
      dynamic_config_slice: config_slice.DynamicConfigSlice,
      geo: geometry.Geometry,
      core_profiles: state_module.CoreProfiles,
      time_step_calculator_state,
      core_transport: state_module.CoreTransport,
  ) -> tuple[jnp.ndarray, tuple[Any, ...]]:
    return jnp.ones(()), ()


class _FakeSimulationStepFn(sim_lib.SimulationStepFn):
  """Fake step function which only calculates new implicit profiles."""

  def __init__(
      self,
      time_step_calculator: ts.TimeStepCalculator,
      source_models: source_models_lib.SourceModels,
  ):
    self._time_step_calculator = time_step_calculator
    # This isn't actually used for stepping in this class.
    self._stepper = explicit_stepper.ExplicitStepper(
        transport_model=constant_transport_model.ConstantTransportModel(),
        source_models=source_models,
    )

  @property
  def stepper(self):
    return self._stepper

  def __call__(
      self,
      input_state: state_module.ToraxSimState,
      geo: geometry.Geometry,
      dynamic_config_slice_provider: config_slice.DynamicConfigSliceProvider,
      static_config_slice: config_slice.StaticConfigSlice,
      explicit_source_profiles: source_profiles_lib.SourceProfiles,
  ) -> state_module.ToraxSimState:
    dt, ts_state = self._time_step_calculator.next_dt(
        dynamic_config_slice=dynamic_config_slice_provider(input_state.t),
        geo=geo,
        core_profiles=input_state.core_profiles,
        time_step_calculator_state=input_state.time_step_calculator_state,
        core_transport=input_state.core_transport,
    )
    new_t = input_state.t + dt
    return dataclasses.replace(
        input_state,
        t=new_t,
        dt=dt,
        time_step_calculator_state=ts_state,
        # The returned source profiles include only the implicit sources.
        core_sources=source_models_lib.build_source_profiles(
            source_models=self.stepper.source_models,
            dynamic_config_slice=dynamic_config_slice_provider(new_t),
            geo=geo,
            core_profiles=input_state.core_profiles,  # no state evolution.
            explicit=False,
        ),
    )


if __name__ == '__main__':
  absltest.main()