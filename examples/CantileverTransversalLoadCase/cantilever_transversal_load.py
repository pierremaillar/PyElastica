import numpy as np
from matplotlib import pyplot as plt
from elastica.boundary_conditions import OneEndFixedRod
from elastica.external_forces import EndpointForces
from elastica.timestepper.symplectic_steppers import PositionVerlet
from elastica.timestepper import integrate
import elastica as ea
from cantilever_transversal_load_postprocessing import (
    plot_video_with_surface,
    adjust_square_cross_section,
    Find_Tip_Position,
)


# setting up test params
n_elem = 19
start = np.zeros((3,))
direction = np.array([0.0, 1.0, 0.0])
normal = np.array([0.0, 0.0, 1.0])
radius = 1
side_length = 0.01
base_length = 0.25 * radius * np.pi
base_radius = 0.01 / (
    np.pi ** (1 / 2)
)  # The Cross-sectional area is 1e-4(we assume its equivalent to a square cross-sectional surface with same area)
base_area = np.pi * base_radius**2
density = 1000
youngs_modulus = 1e9
poisson_ratio = 0
shear_modulus = youngs_modulus / (poisson_ratio + 1.0)


def cantilever_subjected_to_a_transversal_load(
    n_elem,
    radius,
    base_length,
    base_radius,
    youngs_modulus,
    load,
    PLOT_FIGURE,
    PLOT_FIGURE_Reach_Equilibrium,
):
    class StretchingBeamSimulator(
        ea.BaseSystemCollection, ea.Constraints, ea.Forcing, ea.Damping, ea.CallBacks
    ):
        pass

    stretch_sim = StretchingBeamSimulator()

    rendering_fps = 30

    density = 1000
    t = np.linspace(0, 0.25 * np.pi, n_elem + 1)
    tmp = np.zeros((3, n_elem + 1), dtype=np.float64)
    tmp[0, :] = -radius * np.cos(t) + 1
    tmp[1, :] = radius * np.sin(t)
    tmp[2, :] *= 0.0
    dir = np.zeros((3, 3, n_elem), dtype=np.float64)
    tan = tmp[:, 1:] - tmp[:, :-1]
    tan = tan / np.linalg.norm(tan, axis=0)

    d1 = np.array([0.0, 0.0, 1.0]).reshape((3, 1))
    d2 = np.cross(tan, d1, axis=0)

    dir[0, :, :] = d1
    dir[1, :, :] = d2
    dir[2, :, :] = tan

    rod = ea.CosseratRod.straight_rod(
        n_elem,
        start,
        direction,
        normal,
        base_length,
        base_radius,
        density,
        youngs_modulus=youngs_modulus,
        shear_modulus=shear_modulus,
        position=tmp,
        directors=dir,
    )

    # Adjust the Cross Section
    adjust_section = adjust_square_cross_section(
        n_elem,
        direction,
        normal,
        base_length,
        base_radius,
        density,
        youngs_modulus=youngs_modulus,
        rod_origin_position=start,
        ring_rod_flag=False,
    )

    rod.mass_second_moment_of_inertia = adjust_section[0]
    rod.inv_mass_second_moment_of_inertia = adjust_section[1]
    rod.bend_matrix = adjust_section[2]

    stretch_sim.append(rod)

    dl = base_length / n_elem
    dt = 0.01 * dl / 50
    step_skip = int(1.0 / (rendering_fps * dt))

    stretch_sim.constrain(rod).using(
        OneEndFixedRod, constrained_position_idx=(0,), constrained_director_idx=(0,)
    )

    print("One end of the rod is now fixed in place")

    stretch_sim.dampen(rod).using(
        ea.AnalyticalLinearDamper,
        damping_constant=0.1,
        time_step=dt,
    )

    ramp_up_time = 1.0

    origin_force = np.array([0.0, 0.0, 0.0])
    end_force = np.array([0.0, 0.0, load])

    stretch_sim.add_forcing_to(rod).using(
        EndpointForces, origin_force, end_force, ramp_up_time=ramp_up_time
    )
    print("Forces added to the rod")

    class AxialStretchingCallBack(ea.CallBackBaseClass):
        """
        Tracks the velocity norms of the rod
        """

        def __init__(self, step_skip: int, callback_params: dict):
            ea.CallBackBaseClass.__init__(self)
            self.every = step_skip
            self.callback_params = callback_params

        def make_callback(self, system, time, current_step: int):
            if current_step % self.every == 0:
                self.callback_params["time"].append(time)
                self.callback_params["step"].append(current_step)
                self.callback_params["position"].append(
                    system.position_collection.copy()
                )
                self.callback_params["com"].append(
                    system.compute_position_center_of_mass()
                )
                self.callback_params["radius"].append(system.radius.copy())
                self.callback_params["velocity"].append(
                    system.velocity_collection.copy()
                )
                self.callback_params["avg_velocity"].append(
                    system.compute_velocity_center_of_mass()
                )

                self.callback_params["center_of_mass"].append(
                    system.compute_position_center_of_mass()
                )
                self.callback_params["velocity_magnitude"].append(
                    (
                        rod.velocity_collection[-1][0] ** 2
                        + rod.velocity_collection[-1][1] ** 2
                        + rod.velocity_collection[-1][2] ** 2
                    )
                    ** 0.5
                )

    recorded_history = ea.defaultdict(list)

    stretch_sim.collect_diagnostics(rod).using(
        AxialStretchingCallBack, step_skip=step_skip, callback_params=recorded_history
    )
    # Finalization and Run the Project
    final_time = 10
    total_steps = int(final_time / dt)
    print("Total steps to take", total_steps)

    stretch_sim.finalize()
    print("System finalized")
    rod.rest_kappa[...] = rod.kappa
    rod.rest_sigma[...] = rod.sigma

    timestepper = PositionVerlet()

    integrate(timestepper, stretch_sim, final_time, total_steps)
    if PLOT_FIGURE:
        fig = plt.figure()
        ax = fig.add_subplot(111, projection="3d")
        pos = rod.position_collection.view()
        ax.plot(pos[0, :], pos[1, :], pos[2, :], "k")
        ax.set_xlabel("X Label")
        ax.set_ylabel("Y Label")
        ax.set_zlabel("Z Label")
        ax.view_init(elev=20, azim=20)
        plt.show()

    if PLOT_FIGURE_Reach_Equilibrium:
        #   plt.plot(recorded_history["time"], recorded_history["position"], lw=2.0,label="position")
        plt.plot(
            recorded_history["time"],
            recorded_history["velocity_magnitude"],
            lw=1.0,
            label="velocity_magnitude",
        )
        plt.xlabel("Time (s)")
        plt.ylabel("Position (m) and Speed (m/s)")
        plt.title("Tip Speed vs. Time")
        plt.legend()
        plt.grid()
        plt.show()

    print(
        "N_elem=",
        n_elem,
        "Tip Position at Equilibrim is",
        Find_Tip_Position(rod, n_elem),
    )

    plot_video_with_surface(
        [recorded_history],
        video_name="cantilever_subjected_to_a_transversal_load.mp4",
        fps=rendering_fps,
        step=1,
        # The following parameters are optional
        x_limits=(-0.0, 0.7),  # Set bounds on x-axis
        y_limits=(-0.0, 0.7),  # Set bounds on y-axis
        z_limits=(-0.0, 0.7),  # Set bounds on z-axis
        dpi=100,  # Set the quality of the image
        vis3D=True,  # Turn on 3D visualization
        vis2D=False,  # Turn on projected (2D) visualization
    )


cantilever_subjected_to_a_transversal_load(
    32,
    radius,
    base_length,
    base_radius,
    youngs_modulus,
    load=3.0,
    PLOT_FIGURE=True,
    PLOT_FIGURE_Reach_Equilibrium=True,
)
cantilever_subjected_to_a_transversal_load(
    32,
    radius,
    base_length,
    base_radius,
    youngs_modulus,
    load=6.0,
    PLOT_FIGURE=True,
    PLOT_FIGURE_Reach_Equilibrium=True,
)
