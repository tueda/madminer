from __future__ import absolute_import, division, print_function, unicode_literals

import six
import shutil
import h5py
import numpy as np
from collections import OrderedDict
import logging


def save_madminer_settings(
    filename,
    parameters,
    benchmarks,
    benchmarks_is_nuisance=None,
    morphing_components=None,
    morphing_matrix=None,
    systematics_arguments=None,
    overwrite_existing_files=True,
):
    """Saves all MadMiner settings into an HDF5 file."""

    io_tag = "w" if overwrite_existing_files else "x"

    with h5py.File(filename, io_tag) as f:

        # Prepare parameters
        parameter_names = [pname for pname in parameters]
        n_parameters = len(parameter_names)
        parameter_names_ascii = [pname.encode("ascii", "ignore") for pname in parameter_names]
        parameter_lha_blocks = [parameters[key][0].encode("ascii", "ignore") for key in parameter_names]
        parameter_lha_ids = np.array([parameters[key][1] for key in parameter_names], dtype=np.int)
        parameter_max_power = np.array([parameters[key][2] for key in parameter_names], dtype=np.int)

        parameter_ranges = np.array([parameters[key][3] for key in parameter_names], dtype=np.float)
        parameter_transforms = []
        for key in parameter_names:
            parameter_transform = parameters[key][4]
            if parameter_transform is None:
                parameter_transform = ""
            parameter_transforms.append(parameter_transform.encode("ascii", "ignore"))

        # Store parameters
        f.create_dataset("parameters/names", (n_parameters,), dtype="S256", data=parameter_names_ascii)
        f.create_dataset("parameters/lha_blocks", (n_parameters,), dtype="S256", data=parameter_lha_blocks)
        f.create_dataset("parameters/lha_ids", data=parameter_lha_ids)
        f.create_dataset("parameters/max_power", data=parameter_max_power)
        f.create_dataset("parameters/ranges", data=parameter_ranges)
        f.create_dataset("parameters/transforms", (n_parameters,), dtype="S256", data=parameter_transforms)

        # Prepare benchmarks
        benchmark_names = [bname for bname in benchmarks]
        n_benchmarks = len(benchmark_names)
        benchmark_names_ascii = [bname.encode("ascii", "ignore") for bname in benchmark_names]
        benchmark_values = np.array(
            [[benchmarks[bname][pname] for pname in parameter_names] for bname in benchmark_names]
        )
        if benchmarks_is_nuisance is None:
            benchmark_is_nuisance = [False for _ in benchmarks]
        benchmark_is_nuisance = np.array(
            [1 if is_nuisance else 0 for is_nuisance in benchmark_is_nuisance], dtype=np.int
        )

        # Store benchmarks
        f.create_dataset("benchmarks/names", (n_benchmarks,), dtype="S256", data=benchmark_names_ascii)
        f.create_dataset("benchmarks/values", data=benchmark_values)
        f.create_dataset("benchmarks/is_nuisance", data=benchmark_is_nuisance)

        # Store morphing info
        if morphing_components is not None:
            f.create_dataset("morphing/components", data=morphing_components.astype(np.int))
        if morphing_matrix is not None:
            f.create_dataset("morphing/morphing_matrix", data=morphing_matrix.astype(np.float))

        # Prepare and store systematics setup
        if systematics_arguments is not None:
            systematics_arguments_ascii = [systematics_arguments.encode("ascii", "ignore")]
            f.create_dataset("systematics/arguments", dtype="S256", data=systematics_arguments_ascii)


def load_madminer_settings(filename, include_nuisance_benchmarks=False):
    """ Loads MadMiner settings, observables, and weights from a HDF5 file. """

    with h5py.File(filename, "r") as f:

        # Parameters
        try:
            parameter_names = f["parameters/names"][()]
            parameter_lha_blocks = f["parameters/lha_blocks"][()]
            parameter_lha_ids = f["parameters/lha_ids"][()]
            parameter_ranges = f["parameters/ranges"][()]
            parameter_max_power = f["parameters/max_power"][()]
            parameter_transforms = f["parameters/transforms"][()]

            parameter_names = [pname.decode("ascii") for pname in parameter_names]
            parameter_lha_blocks = [pblock.decode("ascii") for pblock in parameter_lha_blocks]
            parameter_transforms = [ptrf.decode("ascii") for ptrf in parameter_transforms]
            parameter_transforms = [None if ptrf == "" else ptrf for ptrf in parameter_transforms]
            parameter_max_power = np.array(parameter_max_power)
            if len(parameter_max_power.shape) < 2:
                parameter_max_power = parameter_max_power.reshape((-1, 1))

            parameters = OrderedDict()

            for pname, prange, pblock, pid, p_maxpower, ptrf in zip(
                parameter_names,
                parameter_ranges,
                parameter_lha_blocks,
                parameter_lha_ids,
                parameter_max_power,
                parameter_transforms,
            ):
                parameters[pname] = (pblock, int(pid), tuple(p_maxpower), tuple(prange), ptrf)

        except KeyError:
            raise IOError("Cannot read parameters from HDF5 file")

        # Benchmarks
        try:
            benchmark_names = f["benchmarks/names"][()]
            benchmark_values = f["benchmarks/values"][()]
        except KeyError:
            raise IOError("Cannot read benchmarks from HDF5 file")

        try:
            benchmark_is_nuisance = f["benchmarks/is_nuisance"][()]
            benchmark_is_nuisance = [False if is_nuisance == 0 else True for is_nuisance in benchmark_is_nuisance]
        except KeyError:
            logging.info("HDF5 file does not contain is_nuisance field. Assuming is_nuisance=False for all benchmarks.")
            benchmark_is_nuisance = [False for _ in benchmark_names]

        reference_benchmark = None
        try:
            benchmark_is_reference = f["benchmarks/is_reference"][()]
            for is_reference, bname in zip(benchmark_is_reference, benchmark_names):
                if is_reference:
                    reference_benchmark = bname
        except KeyError:
            logging.info("HDF5 file does not contain is_reference field.")

        benchmark_names = [bname.decode("ascii") for bname in benchmark_names]

        benchmarks = OrderedDict()

        for bname, bvalue_matrix, is_nuisance in zip(benchmark_names, benchmark_values, benchmark_is_nuisance):
            if include_nuisance_benchmarks or (not is_nuisance):
                bvalues = OrderedDict()
                for pname, pvalue in zip(parameter_names, bvalue_matrix):
                    bvalues[pname] = pvalue

                benchmarks[bname] = bvalues

        # Morphing
        try:
            morphing_components = np.asarray(f["morphing/components"][()], dtype=np.int)
            morphing_matrix = np.asarray(f["morphing/morphing_matrix"][()])

        except KeyError:
            morphing_components = None
            morphing_matrix = None

        # Observables
        try:
            observables = OrderedDict()

            observable_names = f["observables/names"][()]
            observable_names = [oname.decode("ascii") for oname in observable_names]
            observable_definitions = f["observables/definitions"][()]
            observable_definitions = [odef.decode("ascii") for odef in observable_definitions]

            for oname, odef in zip(observable_names, observable_definitions):
                observables[oname] = odef
        except KeyError:
            observables = None

        # Number of samples
        try:
            observations = f["samples/observations"]
            weights = f["samples/weights"]

            n_samples = observations.shape[0]

            if weights.shape[0] != n_samples:
                raise ValueError("Number of weights and observations don't match: {}, {}", weights.shape[0], n_samples)

        except KeyError:
            n_samples = 0

        # Systematics setup
        try:
            systematics_arguments = f["systematics/arguments"][0].decode("ascii")
        except KeyError:
            systematics_arguments = None

        return (
            parameters,
            benchmarks,
            benchmark_is_nuisance,
            morphing_components,
            morphing_matrix,
            observables,
            n_samples,
            systematics_arguments,
            reference_benchmark,
        )


def madminer_event_loader(
    filename,
    start=0,
    end=None,
    batch_size=100000,
    include_nuisance_parameters=True,
    benchmark_is_nuisance=None,
    include_sampling_information=False,
):
    # Nuisance parameter filtering
    if not include_nuisance_parameters:
        if benchmark_is_nuisance is None:
            logging.warning(
                "include_nuisance_parameters=False without benchmark_is_nuisance information. Returning all weights."
            )
            include_nuisance_parameters = True
        else:
            benchmark_filter = np.logical_not(np.array(benchmark_is_nuisance, dtype=np.bool))

    with h5py.File(filename, "r") as f:

        # Handles to data
        try:
            observations = f["samples/observations"]
            weights = f["samples/weights"]
        except KeyError:
            logging.warning("No events found!")
            return

        if include_sampling_information:
            try:
                sampled_from = f["samples/sampled_from_benchmark"]
            except KeyError:
                logging.warning("No sampling information stored in file {}".format(filename))
                sampled_from = None

        # Preparations
        n_samples = observations.shape[0]
        if weights.shape[0] != n_samples:
            raise ValueError("Number of weights and observations don't match: {}, {}", weights.shape[0], n_samples)

        if end is None:
            end = n_samples
        end = min(n_samples, end)

        if batch_size is None:
            batch_size = n_samples

        current = start

        # Loop over data
        while current < end:
            this_end = min(current + batch_size, end)

            this_observations = np.array(observations[current:this_end])
            if include_nuisance_parameters:
                this_weights = np.array(weights[current:this_end])
            else:
                this_weights = np.array(weights[current:this_end, benchmark_filter])
            if include_sampling_information:
                this_sampled_from = None if sampled_from is None else np.array(sampled_from[current:this_end])

                # As a temporary solution, here's a hack:
                # TODO: remove this!
                if this_sampled_from is None:
                    this_sampled_from = np.array([0 for _ in this_observations])

                yield (this_observations, this_weights, this_sampled_from)
            else:
                yield (this_observations, this_weights)

            current += batch_size


def load_benchmarks_from_madminer_file(filename, include_nuisance_benchmarks=False):
    with h5py.File(filename, "r") as f:

        # Benchmarks
        try:
            benchmark_names = f["benchmarks/names"][()]
            benchmark_names = [bname.decode("ascii") for bname in benchmark_names]

            logging.debug("Benchmarks found in MadMiner file: %s", benchmark_names)

        except KeyError:
            raise IOError("Cannot read benchmarks from HDF5 file")

        if not include_nuisance_benchmarks:
            try:
                benchmark_is_nuisance = f["benchmarks/is_nuisance"][()]
                benchmark_is_nuisance = [False if is_nuisance == 0 else True for is_nuisance in benchmark_is_nuisance]
            except KeyError:
                logging.info(
                    "HDF5 file does not contain is_nuisance field. Assuming is_nuisance=False for all benchmarks."
                )
                benchmark_is_nuisance = [False for _ in benchmark_names]

            phys_benchmark_names = []
            for name, is_nuisance in zip(benchmark_names, benchmark_is_nuisance):
                if not is_nuisance:
                    phys_benchmark_names.append(name)

            return phys_benchmark_names

        return benchmark_names


def save_preformatted_events_to_madminer_file(
    filename, observations, weights, copy_setup_from, overwrite_existing_samples=True
):
    if copy_setup_from is not None:
        try:
            shutil.copyfile(copy_setup_from, filename)
        except IOError:
            if not overwrite_existing_samples:
                raise ()

    io_tag = "a"  # Read-write if file exists, otherwise create

    with h5py.File(filename, io_tag) as f:

        # Check if groups exist already
        if overwrite_existing_samples:
            try:
                del f["samples"]
            except Exception:
                pass

        # Save weights
        f.create_dataset("samples/weights", data=weights)

        # Prepare observable values
        f.create_dataset("samples/observations", data=observations)


def save_nuisance_benchmarks_to_madminer_file(
    filename, weight_names, reference_benchmark=None, sort=True, copy_from=None
):
    """ Saves the names of nuisance-defined benchmarks in an HDF5 file """

    # Copy file
    if copy_from is not None:
        try:
            shutil.copyfile(copy_from, filename)
        except IOError:
            pass

    # Sort weight names
    if sort:
        weight_names = sorted(weight_names)

    io_tag = "a"  # Read-write if file exists, otherwise create

    with h5py.File(filename, io_tag) as f:

        # Load existing benchmarks
        try:
            benchmark_names = list(f["benchmarks/names"][()])
            benchmark_values = list(f["benchmarks/values"][()])
        except KeyError:
            raise IOError("Cannot read benchmarks from HDF5 file")

        benchmark_names = [bname.decode("ascii") for bname in benchmark_names]

        try:
            benchmark_is_nuisance = list(f["benchmarks/is_nuisance"][()])
            benchmark_is_nuisance = [False if is_nuisance == 0 else True for is_nuisance in benchmark_is_nuisance]
        except KeyError:
            logging.info("HDF5 file does not contain is_nuisance field. Assuming is_nuisance=False for all benchmarks.")
            benchmark_is_nuisance = [False for _ in benchmark_names]

        logging.debug("Benchmarks found in HDF5 file: %s", benchmark_names)

        # Add weights not found before
        for weight_name in weight_names:
            if weight_name in benchmark_names:
                logging.debug("Benchmark %s already in benchmark_names", weight_name)
                continue

            logging.debug("Adding nuisance benchmark %s", weight_name)

            benchmark_names.append(weight_name)
            benchmark_is_nuisance.append(True)
            benchmark_values.append(np.zeros_like(benchmark_values[0]))

        # Prepare benchmarks for saving
        n_benchmarks = len(benchmark_names)
        benchmark_names_ascii = [bname.encode("ascii", "ignore") for bname in benchmark_names]
        benchmark_values = np.array(benchmark_values)
        benchmark_is_nuisance = np.array(
            [1 if is_nuisance else 0 for is_nuisance in benchmark_is_nuisance], dtype=np.int
        )
        benchmark_is_reference = np.array(
            [1 if bname == reference_benchmark else 0 for bname in benchmark_names], dtype=np.int
        )

        logging.debug("Combined benchmark names: %s", benchmark_names)
        logging.debug("Combined is_nuisance: %s", benchmark_is_nuisance)
        logging.debug("Combined is_reference: %s", benchmark_is_reference)

        # Make room for saving all this glorious data
        del f["benchmarks"]

        # Store benchmarks
        f.create_dataset("benchmarks/names", (n_benchmarks,), dtype="S256", data=benchmark_names_ascii)
        f.create_dataset("benchmarks/values", data=benchmark_values)
        f.create_dataset("benchmarks/is_nuisance", data=benchmark_is_nuisance)
        f.create_dataset("benchmarks/is_reference", data=benchmark_is_reference)


def save_events_to_madminer_file(
    filename,
    observables,
    observations,
    weights,
    sampled_from_benchmark=None,
    copy_from=None,
    overwrite_existing_samples=True,
):
    if copy_from is not None:
        try:
            shutil.copyfile(copy_from, filename)
        except IOError:
            if not overwrite_existing_samples:
                raise ()

    io_tag = "a"  # Read-write if file exists, otherwise create

    with h5py.File(filename, io_tag) as f:

        # Check if groups exist already
        if overwrite_existing_samples:
            try:
                del f["observables"]
                del f["samples"]
            except Exception:
                pass

        if observables is not None:
            # Prepare observable definitions
            observable_names = [oname for oname in observables]
            n_observables = len(observable_names)
            observable_names_ascii = [oname.encode("ascii", "ignore") for oname in observable_names]
            observable_definitions = []
            for key in observable_names:
                definition = observables[key]
                if isinstance(definition, six.string_types):
                    observable_definitions.append(definition.encode("ascii", "ignore"))
                else:
                    observable_definitions.append("".encode("ascii", "ignore"))

            # Store observable definitions
            f.create_dataset("observables/names", (n_observables,), dtype="S256", data=observable_names_ascii)
            f.create_dataset("observables/definitions", (n_observables,), dtype="S256", data=observable_definitions)

        if weights is not None and observations is not None:
            # Try to find benchmarks in file
            logging.debug("Weight names found in Delphes files: %s", [key for key in weights])
            try:
                benchmark_names = f["benchmarks/names"][()]
                benchmark_names = [bname.decode("ascii") for bname in benchmark_names]

                logging.debug("Benchmarks found in MadMiner file: %s", benchmark_names)

                # Sort weights: First the benchmarks in the right order, then the rest alphabetically
                weights_sorted = []
                for key in benchmark_names:
                    weights_sorted.append(weights[key])
                for key in sorted(weights.keys()):
                    if key not in benchmark_names:
                        weights_sorted.append(key)

                logging.debug("Sorted benchmarks: %s", benchmark_names)

            except Exception as e:
                logging.warning("Issue matching weight names in HepMC file to benchmark names in MadMiner file:\n%s", e)

                weights_sorted = [weights[key] for key in weights]

            # Save weights
            weights_sorted = np.array(weights_sorted)
            weights_sorted = weights_sorted.T  # Shape (n_events, n_weights)
            f.create_dataset("samples/weights", data=weights_sorted)

            # Prepare and save observable values
            observations = np.array([observations[oname] for oname in observable_names]).T
            f.create_dataset("samples/observations", data=observations)

            # Sampling information (needed for nuisance morphing)
            if sampled_from_benchmark is not None:
                sampled_from_benchmark_indices = []
                for name in benchmark_names:
                    try:
                        sampled_from_benchmark_indices.append(benchmark_names.index(name))
                    except ValueError:
                        logging.error(
                            "Could not find sampling benchmark %s in benchmark names %s. Not saving sampling "
                            "information (this might break nuisance parameter analyses).",
                            name,
                            benchmark_names,
                        )
                        return

                # Store sampling information
                sampled_from_benchmark_indices = np.array(sampled_from_benchmark_indices)
                f.create_dataset("samples/sampled_from_benchmark", data=sampled_from_benchmark_indices)


def save_madminer_file_from_lhe(
    filename, observables, observations, weights, copy_from=None, overwrite_existing_samples=True
):
    if copy_from is not None:
        try:
            shutil.copyfile(copy_from, filename)
        except IOError:
            if not overwrite_existing_samples:
                raise ()

    io_tag = "a"  # Read-write if file exists, otherwise create

    with h5py.File(filename, io_tag) as f:

        # Check if groups exist already
        if overwrite_existing_samples:
            try:
                del f["observables"]
                del f["samples"]
            except Exception:
                pass

        if observables is not None:
            # Prepare observable definitions
            observable_names = [oname for oname in observables]
            n_observables = len(observable_names)
            observable_names_ascii = [oname.encode("ascii", "ignore") for oname in observable_names]
            observable_definitions = []
            for key in observable_names:
                definition = observables[key]
                if isinstance(definition, six.string_types):
                    observable_definitions.append(definition.encode("ascii", "ignore"))
                else:
                    observable_definitions.append("".encode("ascii", "ignore"))

            # Store observable definitions
            f.create_dataset("observables/names", (n_observables,), dtype="S256", data=observable_names_ascii)
            f.create_dataset("observables/definitions", (n_observables,), dtype="S256", data=observable_definitions)

        # Save weights
        weights_event_benchmark = weights.T
        f.create_dataset("samples/weights", data=weights_event_benchmark)

        # Prepare observable values
        observations = np.array([observations[oname] for oname in observable_names]).T
        f.create_dataset("samples/observations", data=observations)
