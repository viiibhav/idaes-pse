##############################################################################
# Institute for the Design of Advanced Energy Systems Process Systems
# Engineering Framework (IDAES PSE Framework) Copyright (c) 2018-2019, by the
# software owners: The Regents of the University of California, through
# Lawrence Berkeley National Laboratory,  National Technology & Engineering
# Solutions of Sandia, LLC, Carnegie Mellon University, West Virginia
# University Research Corporation, et al. All rights reserved.
#
# Please see the files COPYRIGHT.txt and LICENSE.txt for full copyright and
# license information, respectively. Both files are also available online
# at the URL "https://github.com/IDAES/idaes-pse".
##############################################################################
"""
Heat Exchanger Models.
"""
from __future__ import division

__author__ = "John Eslick"

import logging
# Import Pyomo libraries
from pyomo.environ import (Reals, Var, sqrt, log, Expression, Constraint,
                           PositiveReals, SolverFactory)
from pyomo.common.config import ConfigBlock, ConfigValue, In
from pyomo.opt import TerminationCondition

# Import IDAES cores
from idaes.core import (ControlVolume0DBlock,
                        declare_process_block_class,
                        EnergyBalanceType,
                        MomentumBalanceType,
                        MaterialBalanceType,
                        UnitModelBlockData,
                        useDefault)
from idaes.core.util.config import is_physical_parameter_block
from idaes.core.util.misc import add_object_reference

_log = logging.getLogger(__name__)


def delta_temperature_lmtd_rule(b, t):
    """
    This is a rule for a temperaure difference expression to calculate
    :math:`\Delta T` in the heat exchanger model using log-mean temperature
    difference (LMTD).  It can be supplied to "delta_temperature_rule"
    HeatExchanger configuration option.
    """
    dT1 = b.side_1.properties_in[t].temperature - \
        b.side_2.properties_out[t].temperature
    dT2 = b.side_1.properties_out[t].temperature - \
        b.side_2.properties_in[t].temperature
    return (dT1 - dT2) / (log(dT1) - log(dT2))


def delta_temperature_amtd_rule(b, t):
    """
    This is a rule for a temperaure difference expression to calculate
    :math:`\Delta T` in the heat exchanger model using arithmetic-mean temperature
    difference (AMTD).  It can be supplied to "delta_temperature_rule"
    HeatExchanger configuration option.
    """
    dT1 = b.side_1.properties_in[t].temperature - \
        b.side_2.properties_out[t].temperature
    dT2 = b.side_1.properties_out[t].temperature - \
        b.side_2.properties_in[t].temperature
    return (dT1 + dT2) * 0.5


def heat_transfer_rule(b, t):
    """
    This is the defulat rule used by the HeatExchanger model to calculate heat
    transfer (:math:`Q = UA\Delta T`).
    """
    return (b.heat_duty[t] ==
            b.heat_transfer_coefficient[t] *
            b.area * b.delta_temperature[t])


def _make_heater_control_volume(o, name, config):
    """
    This is seperated from the main heater class so it can be reused to create
    control volumes for different types of heat exchange models.
    """
    control_volume = ControlVolume0DBlock(default={
        "dynamic": config.dynamic,
        "property_package": config.property_package,
        "property_package_args": config.property_package_args})
    # we have to attach this control volume to the model for the rest of
    # the steps to work
    setattr(o, name, control_volume)
    # Add inlet and outlet state blocks to control volume
    control_volume.add_state_blocks(
        has_phase_equilibrium=config.calculate_phase_equilibrium,
        package_arguments=config.property_package_args)

    # Add material balance
    control_volume.add_material_balances(
        balance_type=config.material_balance_type,
        has_phase_equilibrium=config.calculate_phase_equilibrium)
    # add energy balance
    control_volume.add_energy_balances(
        balance_type=config.energy_balance_type,
        has_heat_transfer=config.has_heat_transfer)
    # add momentum balance
    control_volume.add_momentum_balances(
        balance_type=config.momentum_balance_type,
        has_pressure_change=config.has_pressure_change)
    return control_volume


def _make_heater_config_block(config):
    """
    Declare configuration options for HeaterData block.
    """
    config.declare("dynamic", ConfigValue(
        domain=In([True, False]),
        default=False,
        description="Dynamic model flag",
        doc="Indicates whether the model is dynamic."))
    config.declare("has_holdup", ConfigValue(
        default=useDefault,
        domain=In([useDefault, True, False]),
        description="Holdup construction flag",
        doc="""Indicates whether holdup terms should be constructed or not.
Must be True if dynamic = True,
**default** - False.
**Valid values:** {
**True** - construct holdup terms,
**False** - do not construct holdup terms}"""))
    config.declare("material_balance_type", ConfigValue(
        default=MaterialBalanceType.componentPhase,
        domain=In(MaterialBalanceType),
        description="Material balance construction flag",
        doc="""Indicates what type of mass balance should be constructed,
**default** - MaterialBalanceType.componentPhase.
**Valid values:** {
**MaterialBalanceType.none** - exclude material balances,
**MaterialBalanceType.componentPhase** - use phase component balances,
**MaterialBalanceType.componentTotal** - use total component balances,
**MaterialBalanceType.elementTotal** - use total element balances,
**MaterialBalanceType.total** - use total material balance.}"""))
    config.declare("energy_balance_type", ConfigValue(
        default=EnergyBalanceType.enthalpyTotal,
        domain=In(EnergyBalanceType),
        description="Energy balance construction flag",
        doc="""Indicates what type of energy balance should be constructed,
**default** - EnergyBalanceType.enthalpyTotal.
**Valid values:** {
**EnergyBalanceType.none** - exclude energy balances,
**EnergyBalanceType.enthalpyTotal** - single ethalpy balance for material,
**EnergyBalanceType.enthalpyPhase** - ethalpy balances for each phase,
**EnergyBalanceType.energyTotal** - single energy balance for material,
**EnergyBalanceType.energyPhase** - energy balances for each phase.}"""))
    config.declare("momentum_balance_type", ConfigValue(
        default=MomentumBalanceType.pressureTotal,
        domain=In(MomentumBalanceType),
        description="Momentum balance construction flag",
        doc="""Indicates what type of momentum balance should be constructed,
**default** - MomentumBalanceType.pressureTotal.
**Valid values:** {
**MomentumBalanceType.none** - exclude momentum balances,
**MomentumBalanceType.pressureTotal** - single pressure balance for material,
**MomentumBalanceType.pressurePhase** - pressure balances for each phase,
**MomentumBalanceType.momentumTotal** - single momentum balance for material,
**MomentumBalanceType.momentumPhase** - momentum balances for each phase.}"""))
    config.declare("has_heat_transfer", ConfigValue(
        default=True,
        domain=In([True, False]),
        description="Heat transfer term construction flag",
        doc="""Indicates whether terms for heat transfer should be constructed,
**default** - False.
**Valid values:** {
**True** - include heat transfer terms,
**False** - exclude heat transfer terms.}"""))
    config.declare("calculate_phase_equilibrium", ConfigValue(
        default=False,
        domain=In([True, False]),
        description="Calculate phase equilibrium in mixed stream",
        doc="""Argument indicating whether phase equilibrium should be
calculated for the resulting mixed stream,
**default** - False.
**Valid values:** {
**True** - calculate phase equilibrium in mixed stream,
**False** - do not calculate equilibrium in mixed stream.}"""))
    config.declare("has_pressure_change", ConfigValue(
        default=False,
        domain=In([True, False]),
        description="Pressure change term construction flag",
        doc="""Indicates whether terms for pressure change should be
constructed,
**default** - False.
**Valid values:** {
**True** - include pressure change terms,
**False** - exclude pressure change terms.}"""))
    config.declare("property_package", ConfigValue(
        default=useDefault,
        domain=is_physical_parameter_block,
        description="Property package to use for control volume",
        doc="""Property parameter object used to define property calculations,
**default** - useDefault.
**Valid values:** {
**useDefault** - use default package from parent model or flowsheet,
**PropertyParameterObject** - a PropertyParameterBlock object.}"""))
    config.declare("property_package_args", ConfigBlock(
        implicit=True,
        description="Arguments to use for constructing property packages",
        doc="""A ConfigBlock with arguments to be passed to a property block(s)
and used when constructing these,
**default** - None.
**Valid values:** {
see property package for documentation.}"""))


def _make_heat_exchanger_config(config):
    """
    Declare configuration options for HeatExchngerData block.
    """
    config.declare("dynamic", ConfigValue(
        domain=In([True, False]),
        default=False,
        description="Dynamic model flag",
        doc="Indicates whether the model is dynamic."))
    config.declare("side_1", ConfigBlock(
        implicit=True,
        description="Config block for side_1",
        doc="""A config block used to construct the side_1 control volume."""))
    config.declare("side_2", ConfigBlock(
        implicit=True,
        description="Config block for side_2",
        doc="""A config block used to construct the side_2 control volume."""))
    _make_heater_config_block(config.side_1)
    _make_heater_config_block(config.side_2)
    config.declare("delta_temperature_rule", ConfigValue(
        default=delta_temperature_lmtd_rule,
        description="Rule for equation for temperature difference"))
    config.declare("heat_transfer_rule", ConfigValue(
        default=heat_transfer_rule,
        description="Rule for heat transfer rate equation"))
    config.declare("heat_transfer_coefficient_rule", ConfigValue(
        default=None,
        description="Rule for equation for heat transfer coefficient"))


@declare_process_block_class("Heater", doc="Simple 0D heater/cooler model.")
class HeaterData(UnitModelBlockData):
    """
    Simple 0D heater unit.
    Unit model to add or remove heat from a material.
    """
    CONFIG = ConfigBlock()
    _make_heater_config_block(CONFIG)

    def build(self):
        """
        Building model
        Args:
            None
        Returns:
            None
        """
        # Call UnitModel.build to setup dynamics
        super(HeaterData, self).build()
        # Add Control Volume
        _make_heater_control_volume(self, "control_volume", self.config)
        # Add Ports
        self.add_inlet_port()
        self.add_outlet_port()
        # Add a convienient reference to heat duty.
        add_object_reference(self, "heat_duty", self.control_volume.heat)


@declare_process_block_class("HeatExchanger",
                             doc="Simple 0D heat exchanger model.")
class HeatExchangerData(UnitModelBlockData):
    """
    Simple 0D heat exchange unit.
    Unit model to transfer heat from one material to another.
    """
    CONFIG = ConfigBlock()
    _make_heat_exchanger_config(CONFIG)

    def build(self):
        """
        Building model
        Args:
            None
        Returns:
            None
        """
        # Call UnitModel.build to setup dynamics
        super(HeatExchangerData, self).build()
        # Add variables
        self.heat_transfer_coefficient = Var(
            self.time_ref,
            domain=PositiveReals,
            initialize=100,
            doc="Overall heat transfer coefficient")
        self.heat_transfer_coefficient.latex_symbol = "U"
        self.area = Var(
            domain=PositiveReals,
            initialize=1000,
            doc="Heat exchange area")
        self.area.fix()
        self.area.latex_symbol = "A"

        # Both sides are dynamic or not, so sync to unit model level flag
        self.config.side_1.dynamic = self.config.dynamic
        self.config.side_2.dynamic = self.config.dynamic
        # Add Control Volumes
        _make_heater_control_volume(self, "side_1", self.config.side_1)
        _make_heater_control_volume(self, "side_2", self.config.side_2)
        # Add Ports
        self.add_inlet_port(name="inlet_1", block=self.side_1)
        self.add_inlet_port(name="inlet_2", block=self.side_2)
        self.add_outlet_port(name="outlet_1", block=self.side_1)
        self.add_outlet_port(name="outlet_2", block=self.side_2)
        # Add convienient references to heat duty.
        add_object_reference(self, "heat_duty", self.side_2.heat)
        self.side_1.heat.latex_symbol = "Q_1"
        self.side_2.heat.latex_symbol = "Q_2"

        # Add a unit level energy balance
        def unit_heat_balance_rule(b, t):
            return 0 == self.side_1.heat[t] + self.side_2.heat[t]
        self.unit_heat_balance = Constraint(
            self.time_ref, rule=unit_heat_balance_rule)
        # Add heat transfer equation
        self.delta_temperature = Expression(
            self.time_ref,
            rule=self.config.delta_temperature_rule,
            doc="Temperature difference driving force for heat transfer")
        self.delta_temperature.latex_symbol = "\\Delta T"
        self.heat_transfer_equation = Constraint(
            self.time_ref, rule=self.config.heat_transfer_rule)
        if self.config.heat_transfer_coefficient_rule is not None:
            self.heat_transfer_coefficient_equation = Constraint(
                self.time_ref, rule=self.config.heat_transfer_coefficient_rule)
        else:
            self.heat_transfer_coefficient.fix()

    def initialize(self, state_args_1=None, state_args_2=None, outlvl=0,
                   solver='ipopt', optarg={'tol': 1e-6}, duty=10000):
        """
        Heat echanger initialization method.
        Args:
            state_args_1 : a dict of arguments to be passed to the property
                initialization for side_1 (see documentation of the specific
                property package) (default = {}).
            state_args_2 : a dict of arguments to be passed to the property
                initialization for side_2 (see documentation of the specific
                property package) (default = {}).
            outlvl : sets output level of initialisation routine
                     * 0 = no output (default)
                     * 1 = return solver state for each step in routine
                     * 2 = return solver state for each step in subroutines
                     * 3 = include solver output infomation (tee=True)
            optarg : solver options dictionary object (default={'tol': 1e-6})
            solver : str indicating which solver to use during
                     initialization (default = 'ipopt')
            duty : an initial guess for the amount of heat transfered
                (default = 10000)
        Returns:
            None
        """

        self.heat_duty.value = duty  # probably best start with a positive duty
        self.side_1.heat.value = duty  # probably best start with a positive duty
        self.side_2.heat.value = duty  # probably best start with a positive duty
        # Set solver options
        if outlvl > 3:
            stee = True
        else:
            stee = False

        opt = SolverFactory(solver)
        opt.options = optarg

        flags1 = self.side_1.initialize(outlvl=outlvl - 1,
                                        optarg=optarg,
                                        solver=solver,
                                        state_args=state_args_1)

        if outlvl > 0:
            _log.info('{} Initialization Step 1a (side_1) Complete.'
                      .format(self.name))

        flags2 = self.side_2.initialize(outlvl=outlvl - 1,
                                        optarg=optarg,
                                        solver=solver,
                                        state_args=state_args_2)

        if outlvl > 0:
            _log.info('{} Initialization Step 1b (side_2) Complete.'
                      .format(self.name))
        # ---------------------------------------------------------------------
        # Solve unit
        results = opt.solve(self, tee=stee)

        if outlvl > 0:
            if results.solver.termination_condition == \
                    TerminationCondition.optimal:
                _log.info('{} Initialization Step 2 Complete.'
                          .format(self.name))
            else:
                _log.warning('{} Initialization Step 2 Failed.'
                             .format(self.name))

        # ---------------------------------------------------------------------
        # Release Inlet state
        self.side_1.release_state(flags1, outlvl - 1)
        self.side_2.release_state(flags2, outlvl - 1)

        if outlvl > 0:
            _log.info('{} Initialization Complete.'.format(self.name))
