# Copyright (C) 2011 Atsushi Togo
# All rights reserved.
#
# This file is part of phonopy.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
# * Redistributions of source code must retain the above copyright
#   notice, this list of conditions and the following disclaimer.
#
# * Redistributions in binary form must reproduce the above copyright
#   notice, this list of conditions and the following disclaimer in
#   the documentation and/or other materials provided with the
#   distribution.
#
# * Neither the name of the phonopy project nor the names of its
#   contributors may be used to endorse or promote products derived
#   from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

import sys
try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO
import io
import dump
import numpy as np
from phonopy.structure.atoms import PhonopyAtoms
from phonopy.structure.atoms import symbol_map, atom_data
from phonopy.structure.symmetry import elaborate_borns_and_epsilon
from phonopy.file_IO import (write_force_constants_to_hdf5,
                             write_FORCE_CONSTANTS)


def parse_set_of_forces(num_atoms,
                        forces_filenames,
                        use_expat=True,
                        verbose=True):
    if verbose:
        sys.stdout.write("counter (file index): ")
    count = 0
    is_parsed = True
    force_sets = []
    force_files = forces_filenames
    for filename in force_files:
        d = dump.dump(filename)
        frame = d.snaps[0]
        atoms = np.array(frame.atoms)
        force_sets.append(atoms[:,5:])
        if verbose:
            sys.stdout.write("%d " % (count+1))
        count += 1
        if not check_forces(force_sets[-1], num_atoms, filename):
            is_parsed = False
    if verbose:
        print('')
    if is_parsed:
        return force_sets
    else:
        return []

def check_forces(forces, num_atom, filename, verbose=True):
    if len(forces) != num_atom:
        if verbose:
            stars = '*' * len(filename)
            sys.stdout.write("\n")
            sys.stdout.write("***************%s***************\n" % stars)
            sys.stdout.write("***** Parsing \"%s\" failed. *****\n" % filename)
            sys.stdout.write("***************%s***************\n" % stars)
        return False
    else:
        return True


def get_drift_forces(forces, filename=None, verbose=True):
    drift_force = np.sum(forces, axis=0) / len(forces)

    if verbose:
        if filename is None:
            print("Drift force: %12.8f %12.8f %12.8f to be subtracted"
                  % tuple(drift_force))
        else:
            print("Drift force of \"%s\" to be subtracted" % filename)
            print("%12.8f %12.8f %12.8f" % tuple(drift_force))
        sys.stdout.flush()

    return drift_force


def create_FORCE_CONSTANTS(filename, is_hdf5, log_level):
    fc_and_atom_types = parse_force_constants(filename)

    if not fc_and_atom_types:
        print('')
        print("\'%s\' dones not contain necessary information." % filename)
        return 1

    force_constants, atom_types = fc_and_atom_types
    if is_hdf5:
        try:
            import h5py
        except ImportError:
            print('')
            print("You need to install python-h5py.")
            return 1

        write_force_constants_to_hdf5(force_constants)
        if log_level > 0:
            print("force_constants.hdf5 has been created from vasprun.xml.")
    else:
        write_FORCE_CONSTANTS(force_constants)
        if log_level > 0:
            print("FORCE_CONSTANTS has been created from vasprun.xml.")

    if log_level > 0:
        print("Atom types: %s" % (" ".join(atom_types)))
    return 0


def parse_force_constants(filename):
    """Return force constants and chemical elements

    Args:
        filename (str): Filename

    Returns:
        tuple: force constants and chemical elements

    """

    vasprun = Vasprun(io.open(filename, "rb"))
    return vasprun.read_force_constants()


#
# read VASP POSCAR
#
def read_vasp(filename, symbols=None):
    with open(filename) as infile:
        lines = infile.readlines()
    return _get_atoms_from_poscar(lines, symbols)


def read_vasp_from_strings(strings, symbols=None):
    return _get_atoms_from_poscar(StringIO(strings).readlines(), symbols)


def _get_atoms_from_poscar(lines, symbols):
    line1 = [x for x in lines[0].split()]
    if _is_exist_symbols(line1):
        symbols = line1

    scale = float(lines[1])

    cell = []
    for i in range(2, 5):
        cell.append([float(x) for x in lines[i].split()[:3]])
    cell = np.array(cell) * scale

    try:
        num_atoms = np.array([int(x) for x in lines[5].split()])
        line_at = 6
    except ValueError:
        symbols = [x for x in lines[5].split()]
        num_atoms = np.array([int(x) for x in lines[6].split()])
        line_at = 7

    expaned_symbols = _expand_symbols(num_atoms, symbols)

    if lines[line_at][0].lower() == 's':
        line_at += 1

    is_scaled = True
    if (lines[line_at][0].lower() == 'c' or
        lines[line_at][0].lower() == 'k'):
        is_scaled = False

    line_at += 1

    positions = []
    for i in range(line_at, line_at + num_atoms.sum()):
        positions.append([float(x) for x in lines[i].split()[:3]])

    if is_scaled:
        atoms = PhonopyAtoms(symbols=expaned_symbols,
                             cell=cell,
                             scaled_positions=positions)
    else:
        atoms = PhonopyAtoms(symbols=expaned_symbols,
                             cell=cell,
                             positions=positions)

    return atoms


def _is_exist_symbols(symbols):
    for s in symbols:
        if not (s in symbol_map):
            return False
    return True


def _expand_symbols(num_atoms, symbols=None):
    expanded_symbols = []
    is_symbols = True
    if symbols is None:
        is_symbols = False
    else:
        if len(symbols) != len(num_atoms):
            is_symbols = False
        else:
            for s in symbols:
                if not s in symbol_map:
                    is_symbols = False
                    break

    if is_symbols:
        for s, num in zip(symbols, num_atoms):
            expanded_symbols += [s] * num
    else:
        for i, num in enumerate(num_atoms):
            expanded_symbols += [atom_data[i+1][1]] * num

    return expanded_symbols


#
# write vasp POSCAR
#
def write_vasp(filename, cell, direct=True):
    """Write crystal structure to a VASP POSCAR style file.

    Parameters
    ----------
    filename : str
        Filename.
    cell : PhonopyAtoms
        Crystal structure.
    direct : bool, optional
        In 'Direct' or not in VASP POSCAR format. Default is True.

    """

    lines = get_vasp_structure_lines(cell, direct=direct)
    with open(filename, 'w') as w:
        w.write("\n".join(lines))


def write_supercells_with_displacements(supercell,
                                        cells_with_displacements,
                                        pre_filename="POSCAR",
                                        width=3):
    write_vasp("SPOSCAR", supercell, direct=True)
    for i, cell in enumerate(cells_with_displacements):
        if cell is not None:
            write_vasp("{pre_filename}-{0:0{width}}".format(
                i + 1,
                pre_filename=pre_filename,
                width=width),
                       cell,
                       direct=True)

def get_scaled_positions_lines(scaled_positions):
    return "\n".join(_get_scaled_positions_lines(scaled_positions))


def _get_scaled_positions_lines(scaled_positions):
    # map into 0 <= x < 1.
    # (the purpose of the second '% 1' is to handle a surprising
    #  edge case for small negative numbers: '-1e-30 % 1 == 1.0')
    unit_positions = scaled_positions % 1 % 1

    return [
        " %19.16f %19.16f %19.16f" % tuple(vec)
        for vec in unit_positions.tolist()  # lists are faster for iteration
    ]


def sort_positions_by_symbols(symbols, positions):
    from collections import Counter

    # unique symbols in order of first appearance in 'symbols'
    reduced_symbols = _unique_stable(symbols)

    # counts of each symbol
    counts_dict = Counter(symbols)
    counts_list = [counts_dict[s] for s in reduced_symbols]

    # sort positions by symbol (using the order defined by reduced_symbols).
    # using a stable sort algorithm matches the behavior of previous versions
    #  of phonopy (but is not otherwise necessary)
    sort_keys = [reduced_symbols.index(i) for i in symbols]
    perm = _argsort_stable(sort_keys)
    sorted_positions = positions[perm]

    return counts_list, reduced_symbols, sorted_positions, perm


def get_vasp_structure_lines(atoms, direct=True, is_vasp5=True):
    (num_atoms,
     symbols,
     scaled_positions,
     sort_list) = sort_positions_by_symbols(atoms.get_chemical_symbols(),
                                            atoms.get_scaled_positions())
    lines = []
    if is_vasp5:
        lines.append("generated by phonopy")
    else:
        lines.append(" ".join(["%s" % s for s in symbols]))
    lines.append("   1.0")
    for a in atoms.get_cell():
        lines.append("  %21.16f %21.16f %21.16f" % tuple(a))
    if is_vasp5:
        lines.append(" ".join(["%s" % s for s in symbols]))
    lines.append(" ".join(["%4d" % n for n in num_atoms]))
    lines.append("Direct")
    lines += _get_scaled_positions_lines(scaled_positions)

    # VASP compiled on some system, ending by \n is necessary to read POSCAR
    # properly.
    lines.append('')

    return lines

# Get all unique values from a iterable.
# Unlike `list(set(iterable))`, this is a stable algorithm;
# items are returned in order of their first appearance.
def _unique_stable(iterable):
    seen_list = []
    seen_set = set()
    for x in iterable:
        if x not in seen_set:
            seen_set.add(x)
            seen_list.append(x)
    return seen_list


# Alternative to `np.argsort(keys)` that uses a stable sorting algorithm
# so that indices tied for the same value are listed in increasing order
def _argsort_stable(keys):
    # Python's built-in sort algorithm is a stable sort
    return sorted(range(len(keys)), key=keys.__getitem__)

class Vasprun(object):
    def __init__(self, fileptr, use_expat=False):
        self._fileptr = fileptr
        self._use_expat = use_expat

    def read_forces(self):
#        vasprun_etree = self._parse_etree_vasprun_xml(tag='varray')
#        return self._get_forces(vasprun_etree)
        return self._get_forces()

    def read_force_constants(self):
        vasprun = self._parse_etree_vasprun_xml()
        return self._get_force_constants(vasprun)

    def _get_forces(self, vasprun_etree):
        forces = []
        for event, element in vasprun_etree:
            if element.attrib['name'] == 'forces':
                for v in element:
                    forces.append([float(x) for x in v.text.split()])
        return np.array(forces)

    def _get_force_constants(self, vasprun_etree):
        fc_tmp = None
        num_atom = 0
        for event, element in vasprun_etree:
            if num_atom == 0:
                atomtypes = self._get_atomtypes(element)
                if atomtypes:
                    num_atoms, elements, elem_masses = atomtypes[:3]
                    num_atom = np.sum(num_atoms)
                    masses = []
                    for n, m in zip(num_atoms, elem_masses):
                        masses += [m] * n

            # Get Hessian matrix (normalized by masses)
            if element.tag == 'varray':
                if element.attrib['name'] == 'hessian':
                    fc_tmp = []
                    for v in element.findall('./v'):
                        fc_tmp.append([float(x)
                                       for x in v.text.strip().split()])

        if fc_tmp is None:
            return False
        else:
            fc_tmp = np.array(fc_tmp)
            if fc_tmp.shape != (num_atom * 3, num_atom * 3):
                return False
            # num_atom = fc_tmp.shape[0] / 3
            force_constants = np.zeros((num_atom, num_atom, 3, 3),
                                       dtype='double')

            for i in range(num_atom):
                for j in range(num_atom):
                    force_constants[i, j] = fc_tmp[i*3:(i+1)*3, j*3:(j+1)*3]

            # Inverse normalization by atomic weights
            for i in range(num_atom):
                for j in range(num_atom):
                    force_constants[i, j] *= -np.sqrt(masses[i] * masses[j])

            return force_constants, elements

    def _get_atomtypes(self, element):
        atom_types = []
        masses = []
        valences = []
        num_atoms = []

        if element.tag == 'array':
            if 'name' in element.attrib:
                if element.attrib['name'] == 'atomtypes':
                    for rc in element.findall('./set/rc'):
                        atom_info = [x.text for x in rc.findall('./c')]
                        num_atoms.append(int(atom_info[0]))
                        atom_types.append(atom_info[1].strip())
                        masses.append(float(atom_info[2]))
                        valences.append(float(atom_info[3]))
                    return num_atoms, atom_types, masses, valences

        return None

    def _parse_etree_vasprun_xml(self, tag=None):
        if self._is_version528():
            return self._parse_by_etree(VasprunWrapper(self._fileptr), tag=tag)
        else:
            return self._parse_by_etree(self._fileptr, tag=tag)

    def _parse_by_etree(self, fileptr, tag=None):
        try:
            import xml.etree.cElementTree as etree
            for event, elem in etree.iterparse(fileptr):
                if tag is None or elem.tag == tag:
                    yield event, elem
        except ImportError:
            print("Python 2.5 or later is needed.")
            print("For creating FORCE_SETS file with Python 2.4, you can use "
                  "phonopy 1.8.5.1 with python-lxml .")
            sys.exit(1)

    def _parse_by_expat(self, fileptr):
        vasprun = VasprunxmlExpat(fileptr)
        vasprun.parse()
        return vasprun.get_forces()[-1]

    def _is_version528(self):
        for line in self._fileptr:
            if '\"version\"' in str(line):
                self._fileptr.seek(0)
                if '5.2.8' in str(line):
                    sys.stdout.write(
                        "\n"
                        "**********************************************\n"
                        "* A special routine was used for VASP 5.2.8. *\n"
                        "**********************************************\n")
                    return True
                else:
                    return False


class VasprunxmlExpat(object):
    def __init__(self, fileptr):
        """Parsing vasprun.xml by Expat

        Parameters
        ----------
        fileptr: binary stream
            Considering compatibility between python2.7 and 3.x, it is prepared
            as follows:

                import io
                io.open(filename, "rb")

        """

        import xml.parsers.expat

        self._fileptr = fileptr

        self._is_forces = False
        self._is_stress = False
        self._is_positions = False
        self._is_symbols = False
        self._is_basis = False
        self._is_volume = False
        self._is_energy = False
        self._is_k_weights = False
        self._is_eigenvalues = False
        self._is_epsilon = False
        self._is_born = False
        self._is_efermi = False
        self._is_generation = False
        self._is_divisions = False
        self._is_NELECT = False

        self._is_v = False
        self._is_i = False
        self._is_rc = False
        self._is_c = False
        self._is_set = False
        self._is_r = False
        self._is_field = False

        self._is_scstep = False
        self._is_structure = False
        self._is_projected = False
        self._is_proj_eig = False
        self._is_field_string = False
        self._is_pseudopotential = False

        self._all_forces = []
        self._all_stress = []
        self._all_points = []
        self._all_lattice = []
        self._all_energies = []
        self._all_volumes = []
        self._born = []
        self._forces = None
        self._stress = None
        self._points = None
        self._lattice = None
        self._energies = None
        self._epsilon = None
        self._born_atom = None
        self._k_weights = None
        self._k_mesh = None
        self._eigenvalues = None
        self._eig_state = [0, 0]
        self._projectors = None
        self._proj_state = [0, 0, 0]
        self._field_val = None
        self._pseudopotentials = []
        self._ps_atom = None

        self._p = xml.parsers.expat.ParserCreate()
        self._p.buffer_text = True
        self._p.StartElementHandler = self._start_element
        self._p.EndElementHandler = self._end_element
        self._p.CharacterDataHandler = self._char_data

        self.efermi = None
        self.symbols = None
        self.NELECT = None

    def parse(self, debug=False):
        import xml.parsers.expat
        if debug:
            self._p.ParseFile(self._fileptr)
            return True
        else:
            try:
                self._p.ParseFile(self._fileptr)
            except xml.parsers.expat.ExpatError:
                return False
            except Exception:
                raise
            else:
                return True

    @property
    def forces(self):
        return np.array(self._all_forces, dtype='double', order='C')

    def get_forces(self):
        return self.forces

    @property
    def stress(self):
        return np.array(self._all_stress, dtype='double', order='C')

    def get_stress(self):
        return self.stress

    @property
    def points(self):
        return np.array(self._all_points, dtype='double', order='C')

    def get_points(self):
        return self.points

    @property
    def lattice(self):
        """All basis vectors of structure optimization steps

        Each basis vectors are in row vectors (a, b, c)

        """
        return np.array(self._all_lattice, dtype='double', order='C')

    def get_lattice(self):
        return self.lattice

    @property
    def volume(self):
        return np.array(self._all_volumes, dtype='double')

    def get_symbols(self):
        return self.symbols

    @property
    def energies(self):
        """
        Returns
        -------
        ndarray
            dtype='double'
            shape=(structure opt. steps, 3)
            [free energy TOTEN, energy(sigma->0), entropy T*S EENTRO]

        """
        return np.array(self._all_energies, dtype='double', order='C')

    def get_energies(self):
        return self.energies

    @property
    def cell(self):
        return PhonopyAtoms(symbols=self.symbols,
                            scaled_positions=self.points[-1],
                            cell=self.lattice[-1])

    def _start_element(self, name, attrs):
        # Used not to collect energies in <scstep>
        if name == 'scstep':
            self._is_scstep = True

        # Used not to collect basis and positions in
        # <structure name="initialpos" >
        # <structure name="finalpos" >
        if name == 'structure':
            if 'name' in attrs.keys():
                self._is_structure = True

        if (self._is_forces or
            self._is_stress or
            self._is_epsilon or
            self._is_born or
            self._is_positions or
            self._is_basis or
            self._is_volume or
            self._is_k_weights or
            self._is_generation):
            if name == 'v':
                self._is_v = True
                if 'name' in attrs.keys():
                    if attrs['name'] == 'divisions':
                        self._is_divisions = True

        if name == 'varray':
            if 'name' in attrs.keys():
                if attrs['name'] == 'forces':
                    self._is_forces = True
                    self._forces = []

                if attrs['name'] == 'stress':
                    self._is_stress = True
                    self._stress = []

                if attrs['name'] == 'weights':
                    self._is_k_weights = True
                    self._k_weights = []

                if (attrs['name'] == 'epsilon' or
                    attrs['name'] == 'epsilon_scf'):
                    self._is_epsilon = True
                    self._epsilon = []

                if not self._is_structure:
                    if attrs['name'] == 'positions':
                        self._is_positions = True
                        self._points = []

                    if attrs['name'] == 'basis':
                        self._is_basis = True
                        self._lattice = []

        if name == 'field':
            if 'type' in attrs:
                if attrs['type'] == 'string':
                    self._is_field_string = True
            else:
                self._is_field = True

        if name == 'generation':
            self._is_generation = True

        if name == 'i':
            if 'name' in attrs.keys():
                if attrs['name'] == 'efermi':
                    self._is_i = True
                    self._is_efermi = True
                if attrs['name'] == 'NELECT':
                    self._is_i = True
                    self._is_NELECT = True
                if not self._is_structure and attrs['name'] == 'volume':
                    self._is_i = True
                    self._is_volume = True

        if self._is_energy and name == 'i':
            self._is_i = True

        if name == 'energy' and (not self._is_scstep):
            self._is_energy = True
            self._energies = []

        if self._is_symbols and name == 'rc':
            self._is_rc = True

        if self._is_symbols and self._is_rc and name == 'c':
            self._is_c = True

        if self._is_born and name == 'set':
            self._is_set = True
            self._born_atom = []

        if self._field_val == 'pseudopotential':
            if name == 'set':
                self._is_set = True
            if name == 'rc' and self._is_set:
                self._is_rc = True
                self._ps_atom = []
            if name == 'c':
                self._is_c = True

        if name == 'array':
            if 'name' in attrs.keys():
                if attrs['name'] == 'atoms':
                    self._is_symbols = True
                    self.symbols = []

                if attrs['name'] == 'born_charges':
                    self._is_born = True

        if self._is_projected and not self._is_proj_eig:
            if name == 'set':
                if 'comment' in attrs.keys():
                    if 'spin' in attrs['comment']:
                        self._projectors.append([])
                        spin_num = int(attrs['comment'].replace("spin", ''))
                        self._proj_state = [spin_num - 1, -1, -1]
                    if 'kpoint' in attrs['comment']:
                        self._projectors[self._proj_state[0]].append([])
                        k_num = int(attrs['comment'].split()[1])
                        self._proj_state[1:3] = k_num - 1, -1
                    if 'band' in attrs['comment']:
                        s, k = self._proj_state[:2]
                        self._projectors[s][k].append([])
                        b_num = int(attrs['comment'].split()[1])
                        self._proj_state[2] = b_num - 1
            if name == 'r':
                self._is_r = True

        if self._is_eigenvalues:
            if name == 'set':
                if 'comment' in attrs.keys():
                    if 'spin' in attrs['comment']:
                        self._eigenvalues.append([])
                        spin_num = int(attrs['comment'].split()[1])
                        self._eig_state = [spin_num - 1, -1]
                    if 'kpoint' in attrs['comment']:
                        self._eigenvalues[self._eig_state[0]].append([])
                        k_num = int(attrs['comment'].split()[1])
                        self._eig_state[1] = k_num - 1
            if name == 'r':
                self._is_r = True

        if name == 'projected':
            self._is_projected = True
            self._projectors = []

        if name == 'eigenvalues':
            if self._is_projected:
                self._is_proj_eig = True
            else:
                self._is_eigenvalues = True
                self._eigenvalues = []

    def _end_element(self, name):
        if name == 'scstep':
            self._is_scstep = False

        if name == 'structure' and self._is_structure:
            self._is_structure = False

        if name == 'varray':
            if self._is_forces:
                self._is_forces = False
                self._all_forces.append(self._forces)

            if self._is_stress:
                self._is_stress = False
                self._all_stress.append(self._stress)

            if self._is_k_weights:
                self._is_k_weights = False

            if self._is_positions:
                self._is_positions = False
                self._all_points.append(self._points)

            if self._is_basis:
                self._is_basis = False
                self._all_lattice.append(self._lattice)

            if self._is_epsilon:
                self._is_epsilon = False

        if name == 'generation':
            if self._is_generation:
                self._is_generation = False

        if name == 'array':
            if self._is_symbols:
                self._is_symbols = False

            if self._is_born:
                self._is_born = False

        if name == 'energy' and (not self._is_scstep):
            self._is_energy = False
            self._all_energies.append(self._energies)

        if name == 'v':
            self._is_v = False
            if self._is_divisions:
                self._is_divisions = False

        if name == 'i':
            self._is_i = False
            if self._is_efermi:
                self._is_efermi = False
            if self._is_NELECT:
                self._is_NELECT = False
            if self._is_volume:
                self._is_volume = False

        if name == 'rc':
            self._is_rc = False
            if self._is_symbols:
                self.symbols.pop(-1)

        if name == 'c':
            self._is_c = False

        if name == 'r':
            self._is_r = False

        if name == 'projected':
            self._is_projected = False

        if name == 'eigenvalues':
            self._is_eigenvalues = False
            if self._is_projected:
                self._is_proj_eig = False

        if name == 'set':
            self._is_set = False
            if self._is_born:
                self._born.append(self._born_atom)
                self._born_atom = None

        if name == 'field':
            self._is_field_string = False
            self._is_field = False

        if self._field_val == 'pseudopotential':
            if name == 'set':
                self._is_set = False
                self._field_val = None
            if name == 'rc' and self._is_set:
                self._is_rc = False
                self._pseudopotentials.append(self._ps_atom)
                self._ps_atom = None
            if name == 'c':
                self._is_c = False

    def _char_data(self, data):
        if self._is_v:
            if self._is_forces:
                self._forces.append(
                    [float(x) for x in data.split()])

            if self._is_stress:
                self._stress.append(
                    [float(x) for x in data.split()])

            if self._is_epsilon:
                self._epsilon.append(
                    [float(x) for x in data.split()])

            if self._is_positions:
                self._points.append(
                    [float(x) for x in data.split()])

            if self._is_basis:
                self._lattice.append(
                    [float(x) for x in data.split()])

            if self._is_k_weights:
                self._k_weights.append(float(data))

            if self._is_born:
                self._born_atom.append(
                    [float(x) for x in data.split()])

            if self._is_generation:
                if self._is_divisions:
                    self._k_mesh = [int(x) for x in data.split()]

        if self._is_i:
            if self._is_energy:
                self._energies.append(float(data.strip()))

            if self._is_efermi:
                self.efermi = float(data.strip())

            if self._is_NELECT:
                self.NELECT = float(data.strip())

            if self._is_volume:
                self._all_volumes.append(float(data.strip()))

        if self._is_c:
            if self._is_symbols:
                self.symbols.append(str(data.strip()))
            if (self._field_val == 'pseudopotential' and
                self._is_set and self._is_rc):
                if len(self._ps_atom) == 0:
                    self._ps_atom.append(int(data.strip()))
                elif len(self._ps_atom) == 1:
                    self._ps_atom.append(data.strip())
                elif len(self._ps_atom) == 2:
                    self._ps_atom.append(float(data.strip()))
                elif len(self._ps_atom) == 3:
                    self._ps_atom.append(float(data.strip()))
                elif len(self._ps_atom) == 4:
                    self._ps_atom.append(data.strip())

        if self._is_r:
            if self._is_projected and not self._is_proj_eig:
                s, k, b = self._proj_state
                vals = [float(x) for x in data.split()]
                self._projectors[s][k][b].append(vals)
            elif self._is_eigenvalues:
                s, k = self._eig_state
                vals = [float(x) for x in data.split()]
                self._eigenvalues[s][k].append(vals)

        if self._is_field_string:
            self._field_val = data.strip()
