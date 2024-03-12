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

"""The `newton_raphson_solve_block` function.

See function docstring for details.
"""

import dataclasses
import functools
from typing import Callable, Union

from absl import logging
import jax
from jax import numpy as jnp
from jax.experimental import host_callback
from torax import calc_coeffs
from torax import config_slice
from torax import fvm
from torax import geometry
from torax import jax_utils
from torax.fvm import block_1d_coeffs
from torax.fvm import cell_variable
from torax.fvm import residual_and_loss
from torax.stepper import predictor_corrector_method

AuxiliaryOutput = block_1d_coeffs.AuxiliaryOutput
Block1DCoeffsCallback = block_1d_coeffs.Block1DCoeffsCallback
InitialGuessMode = fvm.InitialGuessMode

INITIAL_GUESS_MODE = InitialGuessMode.LINEAR
MAXITER = 30
TOL = 1e-6
DELTA_REDUCTION_FACTOR = 0.5
TAU_MIN = 0.01
# Delta is a vector. If no entry of delta is above this magnitude, we terminate
# the delta loop. This is mostly to avoid getting stuck in an infinite loop in
# cases of bad numerics.
MIN_DELTA = 1e-3


# TODO(b/323504363): considering merging with spectator mechanism
def _log_iterations(
    residual: jax.Array,
    iterations: jax.Array,
    delta_reduction: jax.Array | None = None,
    dt: jax.Array | None = None,
) -> None:
  """Logs info on internal Newton-Raphson iterations.

  NOTE: This function uses jax.experimental.host_callback() to do the logging,
  which means that any code that uses this function will NOT work with JAX's
  compilation cache. Disable logging to use the compilation cache.

  Args:
    residual: Scalar residual.
    iterations: Number of iterations taken so far in the solve block.
    delta_reduction: Current tau used in this iteration.
    dt: Current dt used in this iteration.
  """
  # pylint: disable=g-long-lambda
  if dt is not None:
    host_callback.id_tap(
        lambda arg, _: logging.info(
            'Iteration: %d. Residual: %.16f. dt = %.6f', arg[0], arg[1], arg[2]
        ),
        (iterations, residual, dt),
    )
  elif delta_reduction is not None:
    host_callback.id_tap(
        lambda arg, _: logging.info(
            'Iteration: %d. Residual: %.16f. tau = %.6f', arg[0], arg[1], arg[2]
        ),
        (iterations, residual, delta_reduction),
    )
  else:
    host_callback.id_tap(
        lambda arg, _: logging.info(
            'Iteration: %d. Residual: %.16f', arg[0], arg[1]
        ),
        (iterations, residual),
    )
  # pylint: enable=g-long-lambda


def newton_raphson_solve_block(
    x_old: tuple[cell_variable.CellVariable, ...],
    x_new_update_fns: tuple[cell_variable.CellVariableUpdateFn, ...],
    dt: jax.Array,
    coeffs_callback: Block1DCoeffsCallback,
    dynamic_config_slice_t: config_slice.DynamicConfigSlice,
    dynamic_config_slice_t_plus_dt: config_slice.DynamicConfigSlice,
    static_config_slice: config_slice.StaticConfigSlice,
    geo: geometry.Geometry,
    theta_imp: Union[jax.Array, float] = 1.0,
    log_iterations: bool = False,
    convection_dirichlet_mode: str = 'ghost',
    convection_neumann_mode: str = 'ghost',
    initial_guess_mode: InitialGuessMode = INITIAL_GUESS_MODE,
    maxiter: int = MAXITER,
    tol: float = TOL,
    delta_reduction_factor: float = DELTA_REDUCTION_FACTOR,
    tau_min: float = TAU_MIN,
) -> tuple[tuple[cell_variable.CellVariable, ...], int, AuxiliaryOutput]:
  # pyformat: disable  # pyformat removes line breaks needed for readability
  """Runs one time step of a Newton-Raphson based root-finding on the equation defined by `coeffs`.

  This solver is relatively generic in that it models diffusion, convection,
  etc. abstractly. The caller must do the problem-specific physics calculations
  to obtain the coefficients for a particular problem.

  This solver uses iterative root finding on the linearized residual
  between two sides of the equation describing a theta method update.

  The linearized residual for a trial x_new is:
  R(x_old) + jacobian(R(x_old))*(x_new - x_old)
  Setting delta = x_new - x_old, we solve the linear system:
  A*x_new = b, with A = jacobian(R(x_old)), b = A*x_old - R(x_old)
  Each successive iteration sets x_new = x_old - delta, until the residual
  or delta is under a tolerance (tol).
  If either the delta step leads to an unphysical state, represented by NaNs in
  the residual, or if the residual doesn't shrink following the delta step,
  then delta is successively reduced by a delta_reduction_factor.
  If tau = delta_now / delta_original is below a tolerance, then the iterations
  stop. If residual > tol then the function exits with an error flag, producing
  either a warning or recalculation with a lower dt.

  Args:
    x_old: Tuple containing CellVariables for each channel with their values at
      the start of the time step.
    x_new_update_fns: Tuple containing callables that update the CellVariables
      in x_new to the correct boundary conditions at time t + dt.
    dt: Discrete time step.
    coeffs_callback: Calculates diffusion, convection etc. coefficients given a
      state. Repeatedly called by the iterative optimizer.
    dynamic_config_slice_t: Runtime configuration for time t (the start time of
      the step). These config params can change from step to step without
      triggering a recompilation.
    dynamic_config_slice_t_plus_dt: Runtime configuration for time t + dt.
    static_config_slice: Static runtime configuration. Changes to these config
      parrams will trigger recompilation
    geo: geometry object used to initialize auxiliary outputs
    theta_imp: Coefficient in [0, 1] determining which solution method to use.
      We solve transient_coeff (x_new - x_old) / dt = theta_imp F(t_new) + (1 -
      theta_imp) F(t_old). Three values of theta_imp correspond to named
      solution methods: theta_imp = 1: Backward Euler implicit method (default).
      theta_imp = 0.5: Crank-Nicolson. theta_imp = 0: Produces results
      equivalent to explicit method, but should not be used because this
      function will needless call the linear algebra solver. Use `sim.
      explicit_update` instead.
    log_iterations: If true, output diagnostic information from within iteration
      loop. NOTE: If this is True, then this function will not be cached in
      JAX's compilation cache, meaning a compiled function that calls this
      method cannot be saved for usage in a later Python process. Turn this off
      to enable the cache.
    convection_dirichlet_mode: See docstring of the `convection_terms` function,
      `dirichlet_mode` argument.
    convection_neumann_mode: See docstring of the `convection_terms` function,
      `neumann_mode` argument.
    initial_guess_mode: chooses the initial_guess for the iterative method,
      either x_old or linear step. When taking the linear step, it is also
      recommended to use Pereverzev-Corrigan terms if the transport coefficients
      are stiff, e.g. from QLKNN. This can be set by setting use_pereverzev =
      True in the solver config.
    maxiter: Quit iterating after this many iterations reached.
    tol: Quit iterating after the average absolute value of the residual is <=
      tol.
    delta_reduction_factor: Multiply by delta_reduction_factor after each failed
      line search step.
    tau_min: minimum delta/delta_original allowed before the newton raphson
      routine resets at a lower timestep

  Returns:
    x_new: Tuple, with x_new[i] giving channel i of x at the next time step
    error: int. 0 signifies residual < tol at exit, 1 signifies residual > tol
    aux_output: Extra auxiliary output from the coeffs_callback.
  """
  # pyformat: enable

  coeffs_old = coeffs_callback(x_old, dynamic_config_slice_t)

  num_channels = len(x_old)

  match initial_guess_mode:
    # LINEAR initial guess will provide the initial guess using the predictor-
    # corrector method if predictor_corrector=True in the solver config
    case InitialGuessMode.LINEAR:
      # returns transport coefficients with additional pereverzev terms
      # if set by config, needed if stiff transport models (e.g. qlknn)
      # are used.
      coeffs_exp_linear = coeffs_callback(
          x_old, dynamic_config_slice_t, allow_pereverzev=True
      )

      # See linear_theta_method.py for comments on the predictor_corrector API
      init_val = (
          x_old,
          calc_coeffs.AuxOutput.build_from_geo(geo),
      )
      init_x_new, _ = predictor_corrector_method.predictor_corrector_method(
          init_val=init_val,
          x_new_update_fns=x_new_update_fns,
          dt=dt,
          coeffs_exp=coeffs_exp_linear,
          coeffs_callback=coeffs_callback,
          dynamic_config_slice_t_plus_dt=dynamic_config_slice_t_plus_dt,
          static_config_slice=static_config_slice,
      )
      init_x_new_vec = jnp.concatenate([var.value for var in init_x_new])
    case InitialGuessMode.X_OLD:
      init_x_new_vec = jnp.concatenate([var.value for var in x_old])
    case _:
      raise ValueError(
          f'Unknown option for first guess in iterations: {initial_guess_mode}'
      )

  # Create a residual() function with only one argument: x_new.
  # The other arguments (dt, x_old, etc.) are fixed.
  residual_fun = functools.partial(
      residual_and_loss.theta_method_block_residual,
      dt=dt,
      x_old=x_old,
      x_new_update_fns=x_new_update_fns,
      coeffs_callback=coeffs_callback,
      coeffs_old=coeffs_old,
      dynamic_config_slice_t_plus_dt=dynamic_config_slice_t_plus_dt,
      theta_imp=theta_imp,
      convection_dirichlet_mode=convection_dirichlet_mode,
      convection_neumann_mode=convection_neumann_mode,
  )

  jacobian_fun = jax.jacfwd(residual_fun, has_aux=True)

  cond_fun = functools.partial(cond, tol=tol, tau_min=tau_min, maxiter=maxiter)
  delta_cond_fun = functools.partial(
      delta_cond,
      residual_fun=residual_fun,
  )
  body_fun = functools.partial(
      body,
      residual_fun=residual_fun,
      jacobian_fun=jacobian_fun,
      delta_cond_fun=delta_cond_fun,
      delta_reduction_factor=delta_reduction_factor,
      log_iterations=log_iterations,
  )

  # initialize state dict being passed around Newton-Raphson iterations
  residual_vec_init_x_new, aux_output_init_x_new = residual_fun(init_x_new_vec)
  initial_state = {
      'x': init_x_new_vec,
      'iterations': jnp.array(0),
      'residual': residual_vec_init_x_new,
      'last_tau': jnp.array(1.0),
      'aux_output': aux_output_init_x_new,
  }

  # log initial state if requested
  if log_iterations:
    _log_iterations(
        residual=residual_scalar(initial_state['residual']),
        iterations=initial_state['iterations'],
        dt=dt,
    )

  # carry out iterations. jax.lax.while needed for JAX-compliance
  output_state = jax.lax.while_loop(cond_fun, body_fun, initial_state)

  x_new_values = jnp.split(output_state['x'], num_channels)
  # Make new CellVariable instances with updated values and constraints.
  x_new = [
      update_boundary_fn(dataclasses.replace(var, value=value))
      for var, value, update_boundary_fn in zip(
          x_old, x_new_values, x_new_update_fns
      )
  ]
  x_new = tuple(x_new)

  # Tell the caller whether or not x_new successfully reduces the residual below
  # the tolerance by providing an extra output, error.
  error = jax.lax.cond(
      residual_scalar(output_state['residual']) > tol,
      lambda: 1,  # Called when True
      lambda: 0,  # Called when False
  )

  return x_new, error, output_state['aux_output']


def residual_scalar(x):
  return jnp.mean(jnp.abs(x))


def cond(
    state: dict[str, jax.Array], tol: float, tau_min: float, maxiter: int
) -> bool:
  """Check if exit condition reached for Newton-Raphson iterations."""
  iteration = state['iterations'][...]
  return jnp.bool_(
      jnp.logical_and(
          jnp.logical_and(
              residual_scalar(state['residual']) > tol, iteration < maxiter
          ),
          state['last_tau'] > tau_min,
      )
  )


def body(
    input_state: dict[str, jax.Array],
    residual_fun,
    jacobian_fun,
    delta_cond_fun,
    delta_reduction_factor,
    log_iterations,
) -> dict[str, jax.Array]:
  """Calculates next guess in Newton-Raphson iteration."""

  delta_body_fun = functools.partial(
      delta_body,
      delta_reduction_factor=delta_reduction_factor,
  )

  a_mat, _ = jacobian_fun(input_state['x'])  # Ignore the aux output here.
  rhs = -input_state['residual']
  # delta = x_new - x_old
  # tau = delta/delta0, where delta0 is the delta that sets the linearized
  # residual to zero. tau < 1 when needed such that x_new meets
  # conditions of reduced residual and valid state quantities.
  # If tau < taumin while residual > tol, then the routine exits with an
  # error flag, leading to either a warning or recalculation at lower dt

  initial_delta_state = {
      'x': input_state['x'],
      'delta': jnp.linalg.solve(a_mat, rhs),
      'tau': jnp.array(1.0),
  }
  output_delta_state = jax.lax.while_loop(
      delta_cond_fun, delta_body_fun, initial_delta_state
  )

  x_new_vec = input_state['x'] + output_delta_state['delta']
  residual_vec_x_new, aux_output_x_new = residual_fun(x_new_vec)
  output_state = {
      'x': x_new_vec,
      'residual': residual_vec_x_new,
      'iterations': jnp.array(input_state['iterations'][...]) + 1,
      'last_tau': output_delta_state['tau'],
      'aux_output': aux_output_x_new,
  }
  if log_iterations:
    _log_iterations(
        residual=residual_scalar(output_state['residual']),
        iterations=output_state['iterations'],
        delta_reduction=output_delta_state['tau'],
    )

  return output_state


def delta_cond(
    delta_state: dict[str, jax.Array],
    residual_fun: Callable[[jax.Array], jax.Array],
) -> bool:
  """Check if delta obtained from Newton step is valid.

  Args:
    delta_state: see `delta_body`.
    residual_fun: Residual function.

  Returns:
    True if the new value of `x` causes any NaNs or has increased the residual
    relative to the old value of `x`.
  """
  x_old = delta_state['x']
  x_new = x_old + delta_state['delta']
  residual_vec_x_old, _ = residual_fun(x_old)
  residual_scalar_x_old = residual_scalar(residual_vec_x_old)
  # Avoid sanity checking inside residual, since we directly
  # afterwards check sanity on the output (NaN checking)
  # // TODO(b/323504363): b/312453092 - consider instead sanity-checking x_new
  with jax_utils.enable_errors(False):
    residual_vec_x_new, _ = residual_fun(x_new)
    residual_scalar_x_new = residual_scalar(residual_vec_x_new)
  return jnp.bool_(
      jnp.logical_and(
          jnp.max(delta_state['delta']) > MIN_DELTA,
          jnp.logical_or(
              residual_scalar_x_old < residual_scalar_x_new,
              jnp.isnan(residual_scalar_x_new),
          ),
      ),
  )


def delta_body(
    input_delta_state: dict[str, jax.Array], delta_reduction_factor: float
) -> dict[str, jax.Array]:
  """Reduces step size for this Newton iteration."""
  output_delta_state = {
      'x': input_delta_state['x'],
      'delta': input_delta_state['delta'] * delta_reduction_factor,
      'tau': jnp.array(input_delta_state['tau'][...]) * delta_reduction_factor,
  }
  return output_delta_state