# Reporting Module - Industry Interface Layer

## Vision
The reporting module serves as the primary **industry-facing interface** for Performa, translating our internal architecture into familiar real estate terminology and formats.

## Core Responsibilities
- **Terminology Translation**: Present `CapitalPlan` as "Sources & Uses", `AbsorptionPlanBase` as "Market Leasing", etc.
- **Industry-Standard Reports**: Generate Argus-style, Rockport-style formats
- **Export Formats**: Excel, PDF, PowerPoint integration
- **Template System**: Customizable report templates for different use cases

## Development Phases

### Phase 1: Foundation (Immediate)
- [ ] Create base `Report` and `ReportTemplate` classes
- [ ] Implement `SourcesAndUsesReport` for development projects
- [ ] Add `DevelopmentSummaryReport` with industry metrics
- [ ] Build terminology mapping system

### Phase 2: Industry-Standard Reports (Near-term)
- [ ] `ConstructionDrawReport` (monthly draw requests)
- [ ] `LeasingStatusReport` (absorption progress)
- [ ] `ProjectCashFlowReport` (monthly/quarterly)
- [ ] `StabilizationReport` (completion metrics)

### Phase 3: Advanced Features (Medium-term)
- [ ] Custom report templates via configuration
- [ ] Automated report scheduling and delivery
- [ ] Report history and versioning
- [ ] Integration with external BI tools

### Phase 4: Export & Integration (Long-term)
- [ ] Excel workbook generation with formulas
- [ ] PowerPoint deck automation
- [ ] PDF generation with charts/graphs
- [ ] API endpoints for report data

## Architecture Principles
- **Keep Internal Models Clean**: Don't pollute core models with presentation logic
- **Industry Terminology**: All user-facing reports use familiar real estate terms
- **Template-Driven**: Reports generated from configurable templates
- **Export-Friendly**: Easy integration with Excel, PowerPoint, email workflows
