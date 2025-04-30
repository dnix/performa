"""Tests for the CashFlowAnalysis class and related analysis logic."""
from datetime import date

import pandas as pd
import pytest

# Import models needed for testing
from performa.asset._analysis import CashFlowAnalysis
from performa.asset._losses import GeneralVacancyLoss, Losses
from performa.asset._property import Property
from performa.asset._revenue import Lease, RentRoll, Tenant
from performa.asset._rollover import RolloverLeaseTerms, RolloverProfile
from performa.core._enums import (
    FrequencyEnum,
    LeaseTypeEnum,
    ProgramUseEnum,
    UnitOfMeasureEnum,
    UponExpirationEnum,
    VacancyLossMethodEnum,
)
from performa.core._timeline import Timeline

# --- Fixtures --- 

@pytest.fixture
def analysis_fixture():
    """Fixture for setting up CashFlowAnalysis tests."""
    # Define Leases with different rollover profiles
    tenant1 = Tenant(id="T1", name="Tenant 1")
    tenant2 = Tenant(id="T2", name="Tenant 2")

    # Profile 1: 2 months downtime
    market_terms1 = RolloverLeaseTerms(term_months=36, rent_psf=50.0, months_vacant=2)
    profile1 = RolloverProfile(
        name="Market Rollover 2mo Vac", 
        upon_expiration=UponExpirationEnum.VACATE, # Triggers market lease
        months_vacant=2, 
        market_terms=market_terms1,
        # Other terms just need to exist
        term_months=market_terms1.term_months,
        renewal_probability=0.0,
        renewal_terms=market_terms1.copy(),
        option_terms=market_terms1.copy()
    )
    lease1 = Lease(
        name="Lease 1 (2mo Vac)", tenant=tenant1, suite="101", floor="1", 
        use_type=ProgramUseEnum.OFFICE, lease_type=LeaseTypeEnum.NNN, area=1000,
        timeline=Timeline.from_dates(date(2024, 1, 1), date(2024, 12, 31)),
        value=48.0, unit_of_measure=UnitOfMeasureEnum.PSF, frequency=FrequencyEnum.ANNUAL,
        upon_expiration=UponExpirationEnum.VACATE,
        rollover_profile=profile1
    )

    # Profile 2: 4 months downtime
    market_terms2 = RolloverLeaseTerms(term_months=60, rent_psf=55.0, months_vacant=4)
    profile2 = RolloverProfile(
        name="Market Rollover 4mo Vac", 
        upon_expiration=UponExpirationEnum.MARKET, # Triggers market lease
        months_vacant=4, 
        market_terms=market_terms2,
        term_months=market_terms2.term_months,
        renewal_probability=0.0, # Ensure market terms used
        renewal_terms=market_terms2.copy(),
        option_terms=market_terms2.copy()
    )
    lease2 = Lease(
        name="Lease 2 (4mo Vac)", tenant=tenant2, suite="102", floor="1", 
        use_type=ProgramUseEnum.OFFICE, lease_type=LeaseTypeEnum.NNN, area=1500,
        timeline=Timeline.from_dates(date(2024, 6, 1), date(2025, 5, 31)), # Rolls mid-analysis
        value=50.0, unit_of_measure=UnitOfMeasureEnum.PSF, frequency=FrequencyEnum.ANNUAL,
        upon_expiration=UponExpirationEnum.MARKET,
        rollover_profile=profile2
    )
    
    # Property Setup
    rent_roll = RentRoll(leases=[lease1, lease2], vacant_suites=[])
    prop = Property(
        name="Analysis Test Prop", property_type="Office", net_rentable_area=2500,
        rent_roll=rent_roll,
        # Add minimal losses config
        losses=Losses(
            general_vacancy=GeneralVacancyLoss(rate=0.05, method=VacancyLossMethodEnum.POTENTIAL_GROSS_REVENUE),
            collection_loss=None
        ),
        address="123 Test St", geography="Test", submarket="Test", market="Test", year_built=2010
        # No expenses needed for this specific test
    )

    # Analysis Setup
    analysis_start = date(2024, 1, 1)
    analysis_end = date(2026, 12, 31) # Long enough to capture rollovers
    analysis = CashFlowAnalysis(
        property=prop, 
        analysis_start_date=analysis_start, 
        analysis_end_date=analysis_end
    )
    
    return analysis, lease1, lease2

# --- Tests for _get_projected_leases Rollover Loss Aggregation --- 

def test_get_projected_leases_aggregates_rollover_loss(analysis_fixture):
    """Test that _get_projected_leases correctly aggregates loss from multiple rollovers."""
    analysis, lease1, lease2 = analysis_fixture
    analysis_periods = analysis._create_timeline().period_index
    
    # --- Expected Loss Calculation --- 
    # Lease 1: Ends 2024-12-31, 2 months vacant (Jan, Feb 2025), Market Rent $50/yr
    market_rent1_monthly = 50.0 / 12
    loss1_monthly = market_rent1_monthly * lease1.area # 50/12 * 1000 = 4166.67
    expected_loss1 = pd.Series(loss1_monthly, index=pd.period_range("2025-01", "2025-02", freq='M'))
    
    # Lease 2: Ends 2025-05-31, 4 months vacant (Jun, Jul, Aug, Sep 2025), Market Rent $55/yr
    market_rent2_monthly = 55.0 / 12
    loss2_monthly = market_rent2_monthly * lease2.area # 55/12 * 1500 = 6875.00
    expected_loss2 = pd.Series(loss2_monthly, index=pd.period_range("2025-06", "2025-09", freq='M'))

    # Combined expected loss
    expected_total_loss = pd.Series(0.0, index=analysis_periods)
    expected_total_loss = expected_total_loss.add(expected_loss1.reindex(analysis_periods, fill_value=0.0), fill_value=0.0)
    expected_total_loss = expected_total_loss.add(expected_loss2.reindex(analysis_periods, fill_value=0.0), fill_value=0.0)
    # --- End Expected Loss Calculation --- 

    # --- Execute --- 
    projected_leases = analysis._get_projected_leases() # This calculates and caches the loss
    cached_loss_series = analysis._calculate_rollover_vacancy_loss_series() # Retrieve cached loss
    # --- End Execute --- 
    
    # --- Assertions --- 
    assert projected_leases is not None
    # Should have initial leases + projected market leases
    # Lease 1 -> Market 1 (starts 2025-03-01) 
    # Lease 2 -> Market 2 (starts 2025-10-01)
    assert len(projected_leases) == 4 
    
    assert isinstance(cached_loss_series, pd.Series)
    pd.testing.assert_series_equal(cached_loss_series, expected_total_loss, check_names=False)
    
    # Check specific periods
    assert cached_loss_series['2025-01'] == pytest.approx(loss1_monthly)
    assert cached_loss_series['2025-02'] == pytest.approx(loss1_monthly)
    assert cached_loss_series['2025-03'] == 0.0 # Lease 1 market starts
    assert cached_loss_series['2025-06'] == pytest.approx(loss2_monthly)
    assert cached_loss_series['2025-09'] == pytest.approx(loss2_monthly)
    assert cached_loss_series['2025-10'] == 0.0 # Lease 2 market starts

# --- Tests for _aggregate_detailed_flows Vacancy Reduction Logic --- 

def test_aggregate_flows_vacancy_reduction_enabled(analysis_fixture):
    """Test general vacancy is reduced by rollover loss when flag is True."""
    analysis, _, _ = analysis_fixture
    # --- Setup: Ensure reduction flag is True --- 
    analysis.property.losses.general_vacancy.reduce_general_vacancy_by_rollover_vacancy = True
    analysis_periods = analysis._create_timeline().period_index

    # --- Calculation --- 
    # 1. Get expected rollover loss (calculated in previous test, but recalculate for clarity)
    rollover_loss_series = analysis._calculate_rollover_vacancy_loss_series()
    
    # 2. Calculate expected Potential Gross Revenue (PGR) - needed for gross vacancy basis
    # This requires running the compute_cf for the *projected* leases
    projected_leases = analysis._get_projected_leases() 
    pgr_series = pd.Series(0.0, index=analysis_periods)
    # We need a minimal lookup_fn for lease compute_cf (won't need property lookups for base rent)
    def mock_lookup(key): return 0.0 
    for lease in projected_leases:
        # Get base rent component (component='base_rent') - represents potential revenue
        cf_dict = lease.compute_cf(lookup_fn=mock_lookup)
        base_rent = cf_dict.get("base_rent", pd.Series(0.0, index=lease.timeline.period_index))
        # Align and add to total PGR
        pgr_series = pgr_series.add(base_rent.reindex(analysis_periods, fill_value=0.0), fill_value=0.0)

    # 3. Calculate expected Gross General Vacancy
    vacancy_rate = analysis.property.losses.general_vacancy.rate
    expected_gross_vacancy = pgr_series * vacancy_rate

    # 4. Calculate expected Net General Vacancy
    expected_net_vacancy = (expected_gross_vacancy - rollover_loss_series).clip(lower=0)
    # --- End Calculation --- 

    # --- Execute Aggregation --- 
    # Trigger the aggregation process (can call the internal method for focused test)
    # Need detailed flows first 
    # Note: _compute_detailed_flows populates _cached_detailed_flows
    analysis._compute_detailed_flows() 
    aggregated_flows = analysis._get_aggregated_flows() # This uses the cached detailed flows
    # --- End Execution --- 

    # --- Assertions --- 
    # Check the final GENERAL_VACANCY_LOSS line item
    final_vacancy_loss = aggregated_flows.get(analysis.property.core._enums.AggregateLineKey.GENERAL_VACANCY_LOSS)
    assert final_vacancy_loss is not None
    pd.testing.assert_series_equal(final_vacancy_loss, expected_net_vacancy, check_names=False)

    # Verify specific periods where reduction occurs (e.g., 2025-01)
    assert final_vacancy_loss['2025-01'] == pytest.approx(max(0, expected_gross_vacancy['2025-01'] - rollover_loss_series['2025-01']))
    # Verify a period with no rollover loss has only gross vacancy
    assert final_vacancy_loss['2024-06'] == pytest.approx(expected_gross_vacancy['2024-06'])

def test_aggregate_flows_vacancy_reduction_disabled(analysis_fixture):
    """Test general vacancy equals gross vacancy when reduction flag is False."""
    analysis, _, _ = analysis_fixture
    # --- Setup: Ensure reduction flag is False --- 
    analysis.property.losses.general_vacancy.reduce_general_vacancy_by_rollover_vacancy = False
    analysis_periods = analysis._create_timeline().period_index

    # --- Calculation --- 
    # Calculate expected Potential Gross Revenue (PGR) 
    projected_leases = analysis._get_projected_leases() 
    pgr_series = pd.Series(0.0, index=analysis_periods)
    def mock_lookup(key): return 0.0
    for lease in projected_leases:
        cf_dict = lease.compute_cf(lookup_fn=mock_lookup)
        base_rent = cf_dict.get("base_rent", pd.Series(0.0, index=lease.timeline.period_index))
        pgr_series = pgr_series.add(base_rent.reindex(analysis_periods, fill_value=0.0), fill_value=0.0)

    # Calculate expected Gross General Vacancy
    vacancy_rate = analysis.property.losses.general_vacancy.rate
    expected_gross_vacancy = pgr_series * vacancy_rate
    # --- End Calculation --- 

    # --- Execute Aggregation --- 
    analysis._compute_detailed_flows()
    aggregated_flows = analysis._get_aggregated_flows()
    # --- End Execution --- 

    # --- Assertions --- 
    final_vacancy_loss = aggregated_flows.get(analysis.property.core._enums.AggregateLineKey.GENERAL_VACANCY_LOSS)
    assert final_vacancy_loss is not None
    # Should equal gross vacancy when disabled
    pd.testing.assert_series_equal(final_vacancy_loss, expected_gross_vacancy, check_names=False)

def test_aggregate_flows_vacancy_reduction_edge_case(analysis_fixture):
    """Test reduction when specific rollover loss exceeds gross vacancy (net should be 0)."""
    analysis, _, _ = analysis_fixture
    # --- Setup: Ensure reduction flag is True and Vacancy Rate is Low --- 
    analysis.property.losses.general_vacancy.reduce_general_vacancy_by_rollover_vacancy = True
    analysis.property.losses.general_vacancy.rate = 0.01 # Very low vacancy rate
    analysis_periods = analysis._create_timeline().period_index

    # --- Calculation --- 
    rollover_loss_series = analysis._calculate_rollover_vacancy_loss_series()
    projected_leases = analysis._get_projected_leases()
    pgr_series = pd.Series(0.0, index=analysis_periods)
    def mock_lookup(key): return 0.0
    for lease in projected_leases:
        cf_dict = lease.compute_cf(lookup_fn=mock_lookup)
        base_rent = cf_dict.get("base_rent", pd.Series(0.0, index=lease.timeline.period_index))
        pgr_series = pgr_series.add(base_rent.reindex(analysis_periods, fill_value=0.0), fill_value=0.0)
    
    vacancy_rate = analysis.property.losses.general_vacancy.rate
    expected_gross_vacancy = pgr_series * vacancy_rate
    # Expected net is clipped at zero
    expected_net_vacancy = (expected_gross_vacancy - rollover_loss_series).clip(lower=0)
    # --- End Calculation --- 

    # --- Execute Aggregation --- 
    analysis._compute_detailed_flows() 
    aggregated_flows = analysis._get_aggregated_flows() 
    # --- End Execution --- 

    # --- Assertions --- 
    final_vacancy_loss = aggregated_flows.get(analysis.property.core._enums.AggregateLineKey.GENERAL_VACANCY_LOSS)
    assert final_vacancy_loss is not None
    pd.testing.assert_series_equal(final_vacancy_loss, expected_net_vacancy, check_names=False)

    # Check a period where rollover loss definitely exceeds gross loss
    period_with_high_rollover = '2025-06' # Lease 2 rollover loss occurs here
    assert rollover_loss_series[period_with_high_rollover] > expected_gross_vacancy[period_with_high_rollover]
    assert final_vacancy_loss[period_with_high_rollover] == 0.0 # Should be clipped to zero

def test_aggregate_flows_vacancy_reduction_egr_basis(analysis_fixture):
    """Test vacancy reduction logic when the basis is Effective Gross Revenue (EGR)."""
    analysis, _, _ = analysis_fixture
    # --- Setup: Ensure reduction flag is True and basis is EGR --- 
    analysis.property.losses.general_vacancy.reduce_general_vacancy_by_rollover_vacancy = True
    analysis.property.losses.general_vacancy.method = VacancyLossMethodEnum.EFFECTIVE_GROSS_REVENUE
    analysis_periods = analysis._create_timeline().period_index

    # --- Calculation --- 
    # 1. Get rollover loss
    rollover_loss_series = analysis._calculate_rollover_vacancy_loss_series()
    
    # 2. Calculate basis (EGR = PGR + Misc - Abatement)
    # Note: Fixture has no Misc Income or Abatements, so EGR basis = PGR basis here.
    # The test still verifies the EGR calculation path is taken in _aggregate_detailed_flows.
    projected_leases = analysis._get_projected_leases()
    pgr_series = pd.Series(0.0, index=analysis_periods)
    misc_series = pd.Series(0.0, index=analysis_periods) # Assume zero misc income from fixture
    abate_series = pd.Series(0.0, index=analysis_periods) # Assume zero abatement from fixture
    def mock_lookup(key): return 0.0 
    for lease in projected_leases:
        cf_dict = lease.compute_cf(lookup_fn=mock_lookup)
        base_rent = cf_dict.get("base_rent", pd.Series(0.0, index=lease.timeline.period_index))
        # In a real scenario with abatements, we would get abate_series here too
        pgr_series = pgr_series.add(base_rent.reindex(analysis_periods, fill_value=0.0), fill_value=0.0)
    
    # Calculate the EGR basis *before* vacancy is applied
    egr_basis_series = pgr_series + misc_series - abate_series 

    # 3. Calculate expected Gross General Vacancy based on EGR
    vacancy_rate = analysis.property.losses.general_vacancy.rate
    expected_gross_vacancy = egr_basis_series * vacancy_rate

    # 4. Calculate expected Net General Vacancy
    expected_net_vacancy = (expected_gross_vacancy - rollover_loss_series).clip(lower=0)
    # --- End Calculation --- 

    # --- Execute Aggregation --- 
    analysis._compute_detailed_flows()
    aggregated_flows = analysis._get_aggregated_flows()
    # --- End Execution --- 

    # --- Assertions --- 
    final_vacancy_loss = aggregated_flows.get(analysis.property.core._enums.AggregateLineKey.GENERAL_VACANCY_LOSS)
    assert final_vacancy_loss is not None
    # Check the final loss matches the net calculation based on EGR
    pd.testing.assert_series_equal(final_vacancy_loss, expected_net_vacancy, check_names=False)

# TODO: Add end-to-end integration tests checking final CF DataFrame outputs

# TODO: Add tests for CashFlowAnalysis._aggregate_detailed_flows vacancy reduction logic 