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

"""Unit tests for torax.geometry."""

import dataclasses

from absl.testing import absltest
from absl.testing import parameterized
import jax
from jax import numpy as jnp
import numpy as np
from torax import geometry
from torax.config import runtime_params as general_runtime_params


class GeometryTest(parameterized.TestCase):
  """Unit tests for the `geometry` module."""

  @parameterized.parameters([
      dict(nr=25, seed=20220930),
  ])
  def test_face_to_cell(self, nr, seed):
    """Compare `face_to_cell` to a PINT reference."""

    rng_state = jax.random.PRNGKey(seed)
    del seed  # Make sure seed isn't accidentally re-used

    # Generate face variables
    rng_use, _ = jax.random.split(rng_state)
    face = jax.random.normal(rng_use, (nr + 1,))
    del rng_use  # Make sure rng_use isn't accidentally re-used

    # Convert face values to cell values using jax code being tested
    cell_jax = geometry.face_to_cell(jnp.array(face))

    # Make ground truth
    cell_np = face_to_cell(nr, face)

    np.testing.assert_allclose(cell_jax, cell_np)

  def test_frozen(self):
    """Test that the Geometry class is frozen."""
    geo = geometry.build_circular_geometry()
    with self.assertRaises(dataclasses.FrozenInstanceError):
      geo.dr = 1.0

  def test_geometry_can_be_input_to_jitted_function(self):
    """Test that the Geometry class can be input to a jitted function."""

    def foo(geo: geometry.Geometry):
      _ = geo  # do nothing.

    foo_jitted = jax.jit(foo)
    runtime_params = general_runtime_params.GeneralRuntimeParams()

    with self.subTest('circular_geometry'):
      geo = geometry.build_circular_geometry()
      # Make sure you can call the function with geo as an arg.
      foo_jitted(geo)

    with self.subTest('CHEASE_geometry'):
      geo = geometry.build_chease_geometry(runtime_params)
      # Make sure you can call the function with geo as an arg.
      foo_jitted(geo)


def face_to_cell(nr, face):
  cell = np.zeros(nr)
  cell[:] = 0.5 * (face[1:] + face[:-1])
  return cell


if __name__ == '__main__':
  absltest.main()
