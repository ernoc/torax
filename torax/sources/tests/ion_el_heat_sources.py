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

"""Tests for ion_el_heat_sources."""

from absl.testing import absltest
from torax.sources import ion_el_heat_sources
from torax.sources import runtime_params
from torax.sources import source
from torax.sources.tests import test_lib


class BremsstrahlungHeatSinkTest(test_lib.SingleProfileSourceTestCase):
  """Tests for BremsstrahlungHeatSink."""

  @classmethod
  def setUpClass(cls):
    super().setUpClass(
        source_class=ion_el_heat_sources.BremsstrahlungHeatSink,
        unsupported_modes=[
            runtime_params.Mode.MODEL_BASED,
        ],
        expected_affected_core_profiles=(source.AffectedCoreProfile.TEMP_EL,),
    )


class ChargeExchangeHeatSinkTest(test_lib.SingleProfileSourceTestCase):
  """Tests for ChargeExchangeHeatSink."""

  @classmethod
  def setUpClass(cls):
    super().setUpClass(
        source_class=ion_el_heat_sources.ChargeExchangeHeatSink,
        unsupported_modes=[
            runtime_params.Mode.MODEL_BASED,
        ],
        expected_affected_core_profiles=(source.AffectedCoreProfile.TEMP_ION,),
    )


class CyclotronRadiationHeatSinkTest(test_lib.SingleProfileSourceTestCase):
  """Tests for CyclotronRadiationHeatSink."""

  @classmethod
  def setUpClass(cls):
    super().setUpClass(
        source_class=ion_el_heat_sources.CyclotronRadiationHeatSink,
        unsupported_modes=[
            runtime_params.Mode.MODEL_BASED,
        ],
        expected_affected_core_profiles=(source.AffectedCoreProfile.TEMP_EL,),
    )


class ECRHHeatSourceTest(test_lib.SingleProfileSourceTestCase):
  """Tests for ECRHHeatSource."""

  @classmethod
  def setUpClass(cls):
    super().setUpClass(
        source_class=ion_el_heat_sources.ECRHHeatSource,
        unsupported_modes=[
            runtime_params.Mode.MODEL_BASED,
        ],
        expected_affected_core_profiles=(source.AffectedCoreProfile.TEMP_EL,),
    )


class ICRHHeatSourceTest(test_lib.SingleProfileSourceTestCase):
  """Tests for ICRHHeatSource."""

  @classmethod
  def setUpClass(cls):
    super().setUpClass(
        source_class=ion_el_heat_sources.ICRHHeatSource,
        unsupported_modes=[
            runtime_params.Mode.MODEL_BASED,
        ],
        expected_affected_core_profiles=(source.AffectedCoreProfile.TEMP_ION,),
    )


class LHHeatSourceTest(test_lib.SingleProfileSourceTestCase):
  """Tests for LHHeatSource."""

  @classmethod
  def setUpClass(cls):
    super().setUpClass(
        source_class=ion_el_heat_sources.LHHeatSource,
        unsupported_modes=[
            runtime_params.Mode.MODEL_BASED,
        ],
        expected_affected_core_profiles=(source.AffectedCoreProfile.TEMP_EL,),
    )


class LineRadiationHeatSinkTest(test_lib.SingleProfileSourceTestCase):
  """Tests for LineRadiationHeatSink."""

  @classmethod
  def setUpClass(cls):
    super().setUpClass(
        source_class=ion_el_heat_sources.LineRadiationHeatSink,
        unsupported_modes=[
            runtime_params.Mode.MODEL_BASED,
        ],
        expected_affected_core_profiles=(source.AffectedCoreProfile.TEMP_EL,),
    )


class NBIElectronHeatSourceTest(test_lib.SingleProfileSourceTestCase):
  """Tests for NBIElectronHeatSource."""

  @classmethod
  def setUpClass(cls):
    super().setUpClass(
        source_class=ion_el_heat_sources.NBIElectronHeatSource,
        unsupported_modes=[
            runtime_params.Mode.MODEL_BASED,
        ],
        expected_affected_core_profiles=(source.AffectedCoreProfile.TEMP_EL,),
    )


class NBIIonHeatSourceTest(test_lib.SingleProfileSourceTestCase):
  """Tests for NBIIonHeatSource."""

  @classmethod
  def setUpClass(cls):
    super().setUpClass(
        source_class=ion_el_heat_sources.NBIIonHeatSource,
        unsupported_modes=[
            runtime_params.Mode.MODEL_BASED,
        ],
        expected_affected_core_profiles=(source.AffectedCoreProfile.TEMP_ION,),
    )


class RecombinationHeatSinkTest(test_lib.SingleProfileSourceTestCase):
  """Tests for RecombinationHeatSink."""

  @classmethod
  def setUpClass(cls):
    super().setUpClass(
        source_class=ion_el_heat_sources.RecombinationHeatSink,
        unsupported_modes=[
            runtime_params.Mode.MODEL_BASED,
        ],
        expected_affected_core_profiles=(source.AffectedCoreProfile.TEMP_EL,),
    )


if __name__ == '__main__':
  absltest.main()
