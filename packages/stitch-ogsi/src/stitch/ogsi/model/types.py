from typing import Literal

GEMSrcKey = Literal["gem"]
WMSrcKey = Literal["wm"]
RMISrcKey = Literal["rmi"]
LLMSrcKey = Literal["llm"]


OGSISrcKey = GEMSrcKey | WMSrcKey | RMISrcKey | LLMSrcKey

LocationType = Literal["Onshore", "Offshore", "Unknown"]


ProductionConventionality = Literal[
    "Conventional", "Unconventional", "Mixed", "Unknown"
]


PrimaryHydrocarbonGroup = Literal[
    "Ultra-Light Oil",
    "Light Oil",
    "Medium Oil",
    "Heavy Oil",
    "Extra-Heavy Oil",
    "Dry Gas",
    "Wet Gas",
    "Acid Gas",
    "Condensate",
    "Mixed",
    "Unknown",
]

FieldStatus = Literal["Producing", "Non-Producing", "Abandoned", "Planned"]
