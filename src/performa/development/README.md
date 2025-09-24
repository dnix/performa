# Performa `development` Module - Institutional Development Modeling Engine

This module provides institutional-grade development modeling capabilities
for the Performa real estate financial modeling framework.

## Key Components

- **DevelopmentProject**: Complete project specification container (now with polymorphic blueprints)
- **DevelopmentAnalysisScenario**: Lifecycle assembler and analysis engine
- **AnyDevelopmentBlueprint**: Polymorphic union type for development blueprints
- **DispositionCashFlow**: Exit strategy cash flow modeling

## Design Pattern

This module uses the **"Asset Factory" pattern** where development blueprints
(OfficeDevelopmentBlueprint, ResidentialDevelopmentBlueprint) create stabilized
assets rather than becoming assets themselves.

## Architecture

The development module enables:
- **Complete project lifecycle modeling** from construction through stabilization
- **Polymorphic blueprint system** supporting multiple asset types
- **Seamless transition** from development to operations
- **Integrated financing** and cash flow modeling
- **Disposition planning** with multiple exit strategies

## Example Usage

```python
from performa.development import DevelopmentProject, AnyDevelopmentBlueprint
from performa.asset.office import OfficeDevelopmentBlueprint
from performa.analysis import run

# Create development project
project = DevelopmentProject(
    property_name="Downtown Office Tower",
    development_blueprint=office_blueprint,
    construction_plan=construction_plan,
    financing_plan=financing_plan
)

# Run development analysis
scenario = run(project, timeline, settings)
results = scenario.get_development_summary()
```

The development module integrates with asset modules to provide comprehensive
project modeling from groundbreaking through stabilized operations. 