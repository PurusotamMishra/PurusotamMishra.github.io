from typing import Any, Dict, List
import os, json, argparse, re

from mitreattack.stix20 import MitreAttackData
from mitreattack.navlayers.manipulators.layerops import LayerOps
from mitreattack.navlayers.core.layer import Layer
from mitreattack.navlayers import UsageLayerGenerator
from mitreattack.navlayers import ToSvg, SVGConfig
from mitreattack.navlayers import ToExcel
from mitreattack import download_stix, release_info

from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("mitre-attack")

# Dictionary to store MitreAttackData objects for each domain
attack_data_sources: Dict[str, MitreAttackData] = {}

def download_stix_data(data_path):
    """Download STIX data for all domains.
    
    This function:
    1. Downloads STIX data for enterprise, mobile, and ics domains
    2. Places all JSON files directly in the specified data_path directory
    
    Args:
        data_path: Path to directory where STIX files should be downloaded.
    
    Returns:
        List[str]: A list of tuples containing (domain, file_path) for each downloaded STIX file
    """
    domains = ["enterprise", "mobile", "ics"]
    stix_file_paths = []
    
    # Create the data directory if it doesn't exist
    if not os.path.exists(data_path):
        os.makedirs(data_path)
    
    # Download STIX data for each domain
    for domain in domains:
        # Get release information
        releases = release_info.STIX21[domain]
        known_hash = releases[release_info.LATEST_VERSION]
        
        # Download STIX data directly to the target path
        download_stix.download_stix(
            stix_version="2.1",
            domain=domain,
            download_dir=data_path,
            release=release_info.LATEST_VERSION,
            known_hash=known_hash,
        )
        
        # Save path to the downloaded file
        domain_key = f"{domain}-attack"
        stix_path = os.path.join(data_path, f"{domain_key}.json")
        stix_file_paths.append((domain, stix_path))
    
    return stix_file_paths

def load_stix_data(data_path):
    """Load all STIX data files from the specified directory into the attack_data_sources dictionary.
    
    Args:
        data_path: Path to the directory containing the STIX JSON files
    """
    domains = ["enterprise", "mobile", "ics"]
    loaded_domains = []
    
    for domain in domains:
        domain_key = f"{domain}-attack"
        stix_path = os.path.join(data_path, "v" + release_info.LATEST_VERSION, f"{domain_key}.json")

        # Check if the file exists before loading
        if os.path.exists(stix_path):
            attack_data_sources[domain_key] = MitreAttackData(stix_path)
            loaded_domains.append(domain)

    return loaded_domains

# Function to get the appropriate MitreAttackData object for a domain
def get_attack_data(domain: str = "enterprise") -> MitreAttackData:
    """Get the MitreAttackData object for the specified domain.
    
    Args:
        domain: Domain name ('enterprise', 'mobile', or 'ics')
        
    Returns:
        MitreAttackData object for the specified domain
    """
    domain_key = f"{domain}-attack"
    
    # Check if domain data is loaded
    if domain_key not in attack_data_sources:
        raise ValueError(f"Domain '{domain}' not loaded. Available domains: {', '.join([d.replace('-attack', '') for d in attack_data_sources.keys()])}")
    
    return attack_data_sources[domain_key]

#####################################################################
# Helper function for formatting MITRE ATT&CK objects
#####################################################################

def format_objects(objects: List[Any], include_description: bool = None, domain: str = "enterprise") -> str:
    """Format a list of MITRE ATT&CK objects into a readable string
    
    Args:
        objects: List of objects to format
        include_description: Whether to include description field (default is None, which is system-determined)
        domain: Domain name ('enterprise', 'mobile', or 'ics')
    
    Returns:
        Formatted string with object information
    """
    formatted_results = []
    
    # Get the appropriate attack data source
    attack_data = get_attack_data(domain)

    for obj in objects:
        result = ""

        # Handle different input formats (direct object or dict with 'object' key)
        if isinstance(obj, dict) and "object" in obj:
            obj = obj["object"]

        # Add source STIX ID of relationship if available
        if hasattr(obj, 'source_ref'):
                attack_id = attack_data.get_object_by_stix_id(obj.source_ref)
                result += f"Source Reference: {obj.source_ref}\n"

        # Build format string based on available attributes
        if hasattr(obj, 'name'):
            result += f"Name: {obj.name}\n"
        
        # Add ID if possible (either directly or via STIX ID)
        if hasattr(obj, 'id'):
                attack_id = attack_data.get_attack_id(obj.id)
                result += f"ID: {attack_id}\n"
        else:
            result += f"ID: {obj.id}\n"
        
        result += f"STIX ID: {obj.id}\n"
        
        # Add description if available and requested
        if include_description and hasattr(obj, 'description'):
            result += f"Description: {obj.description}\n"
            
        # Add aliases if available
        if hasattr(obj, 'aliases'):
            result += f"Aliases: {obj.aliases}\n"
            
        formatted_results.append(result.strip())
    
    return "\n---\n".join(formatted_results)


#####################################################################
# Basic object lookup functions
#####################################################################

@mcp.tool()
async def get_object_by_attack_id(attack_id: str, stix_type: str, domain: str = "enterprise", include_description: bool = False) -> str:
    """Get object by ATT&CK ID (case-sensitive)

    Args:
        attack_id: ATT&CK ID to find associated object for
        stix_type: TheSTIX object type (must be 'attack-pattern', 'malware', 'tool', 'intrusion-set',
            'campaign', 'course-of-action', 'x-mitre-matrix', 'x-mitre-tactic',
            'x-mitre-data-source', 'x-mitre-data-component', or 'x-mitre-asset')
        domain: Domain name ('enterprise', 'mobile', or 'ics')
        include_description: Whether to include description in the output (default is False)
    """
    attack_data = get_attack_data(domain)
    object = attack_data.get_object_by_attack_id(attack_id, stix_type)
    return format_objects([object], include_description=include_description, domain=domain)


@mcp.tool()
async def get_object_by_stix_id(stix_id: str, domain: str = "enterprise", include_description: bool = False) -> str:
    """Get object by STIX ID (case-sensitive)

    Args:
        stix_id: ATT&CK ID to find associated object for
        domain: Domain name ('enterprise', 'mobile', or 'ics')
        include_description: Whether to include description in the output (default is False)
    """
    attack_data = get_attack_data(domain)
    object = attack_data.get_object_by_stix_id(stix_id)
    return format_objects([object], include_description=include_description, domain=domain)


@mcp.tool()
async def get_objects_by_name(name: str, stix_type: str, domain: str = "enterprise", include_description: bool = False) -> str:
    """Get objects by name (case-sensitive)

    Args:
        name: Name of the object to search for
        stix_type: TheSTIX object type (must be 'attack-pattern', 'malware', 'tool', 'intrusion-set',
            'campaign', 'course-of-action', 'x-mitre-matrix', 'x-mitre-tactic',
            'x-mitre-data-source', 'x-mitre-data-component', or 'x-mitre-asset')
        domain: Domain name ('enterprise', 'mobile', or 'ics')
        include_description: Whether to include description in the output (default is False)
    """
    attack_data = get_attack_data(domain)
    objects = attack_data.get_objects_by_name(name, stix_type)
    return format_objects(objects, include_description=include_description, domain=domain)


@mcp.tool()
async def get_objects_by_content(content: str, object_type: str, domain: str = "enterprise", include_description: bool = False) -> str:
    """Get objects by the content of their description

    Args:
        name: Name of the object to search for
        object_type: The STIX object type (must be 'attack-pattern', 'malware', 'tool', 'intrusion-set',
            'campaign', 'course-of-action', 'x-mitre-matrix', 'x-mitre-tactic',
            'x-mitre-data-source', 'x-mitre-data-component', or 'x-mitre-asset')
        domain: Domain name ('enterprise', 'mobile', or 'ics')
        include_description: Whether to include description in the output (default is False)
    """
    attack_data = get_attack_data(domain)
    objects = attack_data.get_objects_by_content(content, object_type)
    return format_objects(objects, include_description=include_description, domain=domain)


@mcp.tool()
async def get_stix_type(stix_id: str, domain: str = "enterprise") -> str:
    """Get object type by stix ID

    Args:
        stix_id: ATT&CK ID to find associated object type for
        domain: Domain name ('enterprise', 'mobile', or 'ics')
    """
    attack_data = get_attack_data(domain)
    stix_type = attack_data.get_stix_type(stix_id)
    return f"STIX Type: {stix_type}"


@mcp.tool()
async def get_attack_id(stix_id: str, domain: str = "enterprise") -> str:
    """Get attack ID for given stix ID

    Args:
        stix_id: STIX ID to find associated ATT&CK ID for
        domain: Domain name ('enterprise', 'mobile', or 'ics')
    """
    attack_data = get_attack_data(domain)
    attack_id = attack_data.get_attack_id(stix_id)
    return f"ATT&CK ID: {attack_id}"


@mcp.tool()
async def get_name(stix_id: str, domain: str = "enterprise") -> str:
    """Get name for given stix ID

    Args:
        stix_id: STIX ID to find associated name for
        domain: Domain name ('enterprise', 'mobile', or 'ics')
    """
    attack_data = get_attack_data(domain)
    name = attack_data.get_name(stix_id)
    return f"Name: {name}"


#####################################################################
# Threat Actor Group functions
#####################################################################

@mcp.tool()
async def get_groups_by_alias(alias: str, domain: str = "enterprise", include_description: bool = False) -> str:
    """Get MITRE ATT&CK group ID and description by their alias

    Args:
        alias: alias of a MITRE ATT&CK group
        domain: Domain name ('enterprise', 'mobile', or 'ics')
        include_description: Whether to include description in the output (default is False)
    """
    attack_data = get_attack_data(domain)
    groups = attack_data.get_groups_by_alias(alias)
    return format_objects(groups, include_description=include_description, domain=domain)


@mcp.tool()
async def get_techniques_used_by_group(group_stix_id: str, domain: str = "enterprise", include_description: bool = False) -> str:
    """Get all MITRE ATT&CK techniques used by group by group STIX ID

    Args:
        group_stix_id: Group STIX ID belonging to requested MITRE ATT&CK group
        domain: Domain name ('enterprise', 'mobile', or 'ics')
        include_description: Whether to include description in the output (default is False)
    """
    attack_data = get_attack_data(domain)
    techniques = attack_data.get_techniques_used_by_group(group_stix_id)
    return format_objects(techniques, include_description=include_description, domain=domain)


@mcp.tool()
async def get_software_used_by_group(group_stix_id: str, domain: str = "enterprise", include_description: bool = False) -> str:
    """Get software used by MITRE ATT&CK group STIX id

    Args:
        group_stix_id: Group STIX ID belonging to requested MITRE ATT&CK group
        domain: Domain name ('enterprise', 'mobile', or 'ics')
        include_description: Whether to include description in the output (default is False)
    """
    attack_data = get_attack_data(domain)
    softwares = attack_data.get_software_used_by_group(group_stix_id)
    return format_objects(softwares, include_description=include_description, domain=domain)


@mcp.tool()
async def get_campaigns_attributed_to_group(group_stix_id: str, domain: str = "enterprise", include_description: bool = False) -> str:
    """Get all campaigns attributed to group by group STIX ID

    Args:
        group_stix_id: Group STIX ID belonging to requested MITRE ATT&CK group
        domain: Domain name ('enterprise', 'mobile', or 'ics')
        include_description: Whether to include description in the output (default is False)
    """
    attack_data = get_attack_data(domain)
    campaigns = attack_data.get_campaigns_attributed_to_group(group_stix_id)
    return format_objects(campaigns, include_description=include_description, domain=domain)


@mcp.tool()
async def get_techniques_used_by_group_software(group_stix_id: str, domain: str = "enterprise", include_description: bool = False) -> str:
    """Get techniques used by group's software

    Args:
        group_stix_id: Group STIX ID to check what software they use, and what techniques that software uses
        domain: Domain name ('enterprise', 'mobile', or 'ics')
        include_description: Whether to include description in the output (default is False)
    """
    attack_data = get_attack_data(domain)
    techniques = attack_data.get_techniques_used_by_group_software(group_stix_id)
    return format_objects(techniques, include_description=include_description, domain=domain)


@mcp.tool()
async def get_groups_using_technique(technique_stix_id: str, domain: str = "enterprise", include_description: bool = False) -> str:
    """Get groups using a technique by its STIX ID

    Args:
        technique_stix_id: Technique STIX ID to check what groups are associated with it. 
        domain: Domain name ('enterprise', 'mobile', or 'ics')
        include_description: Whether to include description in the output (default is False)
    """
    attack_data = get_attack_data(domain)
    groups = attack_data.get_groups_using_technique(technique_stix_id)
    return format_objects(groups, include_description=include_description, domain=domain)


@mcp.tool()
async def get_groups_using_software(software_stix_id: str, domain: str = "enterprise", include_description: bool = False) -> str:
    """Get groups using software by software name

    Args:
        software_stix_id: Software STIX ID to check which groups use the given software
        domain: Domain name ('enterprise', 'mobile', or 'ics')
        include_description: Whether to include description in the output (default is False)
    """
    attack_data = get_attack_data(domain)
    groups = attack_data.get_groups_using_software(software_stix_id)
    return format_objects(groups, include_description=include_description, domain=domain)


@mcp.tool()
async def get_groups_attributing_to_campaign(campaign_stix_id: str, domain: str = "enterprise", include_description: bool = False) -> str:
    """Get groups attributing to campaign

    Args:
        campaign_stix_id: Campaign STIX ID to look up what groups have been attributed to it
        domain: Domain name ('enterprise', 'mobile', or 'ics')
        include_description: Whether to include description in the output (default is False)
    """
    attack_data = get_attack_data(domain)
    groups = attack_data.get_groups_attributing_to_campaign(campaign_stix_id)
    return format_objects(groups, include_description=include_description, domain=domain)


#####################################################################
# Software functions
#####################################################################

@mcp.tool()
async def get_software_by_alias(alias: str, domain: str = "enterprise", include_description: bool = False) -> str:
    """Get software by it's alias

    Args:
        alias: Software name alias to find in MITRE ATT&CK
        domain: Domain name ('enterprise', 'mobile', or 'ics')
        include_description: Whether to include description in the output (default is False)
    """
    attack_data = get_attack_data(domain)
    softwares = attack_data.get_software_by_alias(alias)
    return format_objects(softwares, include_description=include_description, domain=domain)


@mcp.tool()
async def get_software_using_technique(technique_stix_id: str, domain: str = "enterprise", include_description: bool = False) -> str:
    """Get software using technique

    Args:
        technique_stix_id: Technique STIX ID to search software that uses it
        domain: Domain name ('enterprise', 'mobile', or 'ics')
        include_description: Whether to include description in the output (default is False)
    """
    attack_data = get_attack_data(domain)
    softwares = attack_data.get_software_using_technique(technique_stix_id)
    return format_objects(softwares, include_description=include_description, domain=domain)


@mcp.tool()
async def get_techniques_used_by_software(software_stix_id: str, domain: str = "enterprise", include_description: bool = False) -> str:
    """Get techniques used by software

    Args:
        software_stix_id: Software STIX ID to check what techniques are associated with it
        domain: Domain name ('enterprise', 'mobile', or 'ics')
        include_description: Whether to include description in the output (default is False)
    """
    attack_data = get_attack_data(domain)
    techniques = attack_data.get_techniques_used_by_software(software_stix_id)
    return format_objects(techniques, include_description=include_description, domain=domain)

#####################################################################
# "Get All" functions for MITRE ATT&CK objects
#####################################################################

@mcp.tool()
async def get_all_techniques(domain: str = "enterprise", include_description: bool = False) -> str:
    """Get all techniques in the MITRE ATT&CK framework
    
    Args:
        domain: Domain name ('enterprise', 'mobile', or 'ics')
        include_description: Whether to include description in the output (default is False)
    """
    attack_data = get_attack_data(domain)
    techniques = attack_data.get_techniques(remove_revoked_deprecated=True)
    return format_objects(techniques, include_description=include_description, domain=domain)


@mcp.tool()
async def get_all_subtechniques(domain: str = "enterprise", include_description: bool = False) -> str:
    """Get all subtechniques in the MITRE ATT&CK framework
    
    Args:
        domain: Domain name ('enterprise', 'mobile', or 'ics')
        include_description: Whether to include description in the output (default is False)
    """
    attack_data = get_attack_data(domain)
    subtechniques = attack_data.get_techniques(remove_revoked_deprecated=True, include_subtechniques=True)
    # Filter to only include subtechniques (those with a parent)
    subtechniques = [t for t in subtechniques if attack_data.get_parent_technique_of_subtechnique(t.id)]
    return format_objects(subtechniques, include_description=include_description, domain=domain)


@mcp.tool()
async def get_all_parent_techniques(domain: str = "enterprise", include_description: bool = False) -> str:
    """Get all parent techniques in the MITRE ATT&CK framework
    
    Args:
        domain: Domain name ('enterprise', 'mobile', or 'ics')
        include_description: Whether to include description in the output (default is False)
    """
    attack_data = get_attack_data(domain)
    techniques = attack_data.get_techniques(remove_revoked_deprecated=True)
    # Filter to only include parent techniques (exclude subtechniques)
    parent_techniques = [t for t in techniques if not '.' in attack_data.get_attack_id(t.id)]
    return format_objects(parent_techniques, include_description=include_description, domain=domain)


@mcp.tool()
async def get_all_groups(domain: str = "enterprise", include_description: bool = False) -> str:
    """Get all threat actor groups in the MITRE ATT&CK framework
    
    Args:
        domain: Domain name ('enterprise', 'mobile', or 'ics')
        include_description: Whether to include description in the output (default is False)
    """
    attack_data = get_attack_data(domain)
    groups = attack_data.get_groups()
    return format_objects(groups, include_description=include_description, domain=domain)


@mcp.tool()
async def get_all_software(domain: str = "enterprise", include_description: bool = False) -> str:
    """Get all software in the MITRE ATT&CK framework
    
    Args:
        domain: Domain name ('enterprise', 'mobile', or 'ics')
        include_description: Whether to include description in the output (default is False)
    """
    attack_data = get_attack_data(domain)
    software = attack_data.get_software()
    return format_objects(software, include_description=include_description, domain=domain)


@mcp.tool()
async def get_all_mitigations(domain: str = "enterprise", include_description: bool = False) -> str:
    """Get all mitigations in the MITRE ATT&CK framework
    
    Args:
        domain: Domain name ('enterprise', 'mobile', or 'ics')
        include_description: Whether to include description in the output (default is False)
    """
    attack_data = get_attack_data(domain)
    mitigations = attack_data.get_mitigations()
    return format_objects(mitigations, include_description=include_description, domain=domain)


@mcp.tool()
async def get_all_tactics(domain: str = "enterprise", include_description: bool = False) -> str:
    """Get all tactics in the MITRE ATT&CK framework
    
    Args:
        domain: Domain name ('enterprise', 'mobile', or 'ics')
        include_description: Whether to include description in the output (default is False)
    """
    attack_data = get_attack_data(domain)
    tactics = attack_data.get_tactics()
    return format_objects(tactics, include_description=include_description, domain=domain)


@mcp.tool()
async def get_all_matrices(domain: str = "enterprise", include_description: bool = False) -> str:
    """Get all matrices in the MITRE ATT&CK framework
    
    Args:
        domain: Domain name ('enterprise', 'mobile', or 'ics')
        include_description: Whether to include description in the output (default is False)
    """
    attack_data = get_attack_data(domain)
    matrices = attack_data.get_matrices()
    return format_objects(matrices, include_description=include_description, domain=domain)


@mcp.tool()
async def get_all_campaigns(domain: str = "enterprise", include_description: bool = False) -> str:
    """Get all campaigns in the MITRE ATT&CK framework
    
    Args:
        domain: Domain name ('enterprise', 'mobile', or 'ics')
        include_description: Whether to include description in the output (default is False)
    """
    attack_data = get_attack_data(domain)
    campaigns = attack_data.get_campaigns()
    return format_objects(campaigns, include_description=include_description, domain=domain)


@mcp.tool()
async def get_all_datasources(domain: str = "enterprise", include_description: bool = False) -> str:
    """Get all data sources in the MITRE ATT&CK framework
    
    Args:
        domain: Domain name ('enterprise', 'mobile', or 'ics')
        include_description: Whether to include description in the output (default is False)
    """
    attack_data = get_attack_data(domain)
    datasources = attack_data.get_datasources()
    return format_objects(datasources, include_description=include_description, domain=domain)


@mcp.tool()
async def get_all_datacomponents(domain: str = "enterprise", include_description: bool = False) -> str:
    """Get all data components in the MITRE ATT&CK framework
    
    Args:
        domain: Domain name ('enterprise', 'mobile', or 'ics')
        include_description: Whether to include description in the output (default is False)
    """
    attack_data = get_attack_data(domain)
    datacomponents = attack_data.get_datacomponents()
    
    # Special handling for datacomponents which need datasource name
    formatted_results = []
    
    for datacomponent in datacomponents:
        datasource = attack_data.get_object_by_stix_id(datacomponent.x_mitre_data_source_ref)
        
        result = (
            f"Name Data Source: {datasource.name}\n"
            f"Name Data Component: {datacomponent.name}\n"
            f"ID: {attack_data.get_attack_id(datasource.id)}\n"
            f"STIX ID: {datacomponent.id}"
        )
        
        if include_description and hasattr(datacomponent, 'description'):
            result += f"\nDescription: {datacomponent.description}"
        
        formatted_results.append(result)
    
    return "\n---\n".join(formatted_results)


@mcp.tool()
async def get_all_assets(domain: str = "ics", include_description: bool = False) -> str:
    """Get all assets in the MITRE ATT&CK framework (ICS domain only)
    
    Args:
        domain: Domain name ('ics')
        include_description: Whether to include description in the output (default is False)
    """
    attack_data = get_attack_data(domain)
    assets = attack_data.get_assets()
    return format_objects(assets, include_description=include_description, domain=domain)

#####################################################################
# Campaign functions
#####################################################################

@mcp.tool()
async def get_campaigns_using_technique(technique_stix_id: str, domain: str = "enterprise", include_description: bool = False) -> str:
    """Get all campaigns in which a technique is used by its STIX ID

    Args:
        technique_stix_id: Technique STIX ID to look up campaigns in which it is used
        domain: Domain name ('enterprise', 'mobile', or 'ics')
        include_description: Whether to include description in the output (default is False)
    """
    attack_data = get_attack_data(domain)
    campaigns = attack_data.get_campaigns_using_technique(technique_stix_id)
    return format_objects(campaigns, include_description=include_description, domain=domain)


@mcp.tool()
async def get_techniques_used_by_campaign(campaign_stix_id: str, domain: str = "enterprise", include_description: bool = False) -> str:
    """Get techniques used by campaign

    Args:
        campaign_stix_id: Campaign STIX ID to check what techniques are used in it
        domain: Domain name ('enterprise', 'mobile', or 'ics')
        include_description: Whether to include description in the output (default is False)
    """
    attack_data = get_attack_data(domain)
    techniques = attack_data.get_techniques_used_by_campaign(campaign_stix_id)
    return format_objects(techniques, include_description=include_description, domain=domain)


@mcp.tool()
async def get_campaigns_using_software(software_stix_id: str, domain: str = "enterprise", include_description: bool = False) -> str:
    """Get all campaigns that use software

    Args:
        software_stix_id: Software STIX ID to look up campaigns in which it is used
        domain: Domain name ('enterprise', 'mobile', or 'ics')
        include_description: Whether to include description in the output (default is False)
    """
    attack_data = get_attack_data(domain)
    campaigns = attack_data.get_campaigns_using_software(software_stix_id)
    return format_objects(campaigns, include_description=include_description, domain=domain)


@mcp.tool()
async def get_software_used_by_campaign(campaign_stix_id: str, domain: str = "enterprise", include_description: bool = False) -> str:
    """Get software used by campaign

    Args:
        campaign_stix_id: Campaign STIX ID to look up what software has been used in it
        domain: Domain name ('enterprise', 'mobile', or 'ics')
        include_description: Whether to include description in the output (default is False)
    """
    attack_data = get_attack_data(domain)
    softwares = attack_data.get_software_used_by_campaign(campaign_stix_id)
    return format_objects(softwares, include_description=include_description, domain=domain)


#####################################################################
# Technique functions
#####################################################################

@mcp.tool()
async def get_techniques_by_platform(platform: str, domain: str = "enterprise", include_description: bool = False) -> str:
    """Get techniques by the platform provided (Windows, Linux etc.)

    Args:
        platform: Platform (Windows, Linux etc.) to find associated techniques for
        domain: Domain name ('enterprise', 'mobile', or 'ics')
        include_description: Whether to include description in the output (default is False)
    """
    attack_data = get_attack_data(domain)
    techniques = attack_data.get_techniques_by_platform(platform)
    return format_objects(techniques, include_description=include_description, domain=domain)


@mcp.tool()
async def get_parent_technique_of_subtechnique(technique_stix_id: str, domain: str = "enterprise", include_description: bool = False) -> str:
    """Get parent technique of subtechnique

    Args:
        technique_stix_id: Subtechnique STIX ID to check what its parent technique is
        domain: Domain name ('enterprise', 'mobile', or 'ics')
        include_description: Whether to include description in the output (default is False)
    """
    attack_data = get_attack_data(domain)
    techniques = attack_data.get_parent_technique_of_subtechnique(technique_stix_id)
    return format_objects(techniques, include_description=include_description, domain=domain)


@mcp.tool()
async def get_subtechniques_of_technique(technique_stix_id: str, domain: str = "enterprise", include_description: bool = False) -> str:
    """Get subtechniques of technique

    Args:
        technique_stix_id: Technique STIX ID to check what its subtechniques are
        domain: Domain name ('enterprise', 'mobile', or 'ics')
        include_description: Whether to include description in the output (default is False)
    """
    attack_data = get_attack_data(domain)
    techniques = attack_data.get_subtechniques_of_technique(technique_stix_id)
    return format_objects(techniques, include_description=include_description, domain=domain)


@mcp.tool()
async def get_techniques_by_tactic(tactic: str, domain: str = "enterprise", include_description: bool = False) -> str:
    """Get all techniques of the given tactic

    Args:
        tactic: Tactic name to lookup techniques for
        domain: Domain name ('enterprise', 'mobile', or 'ics')
        include_description: Whether to include description in the output (default is False)
    """
    attack_data = get_attack_data(domain)
    techniques = attack_data.get_techniques_by_tactic(tactic, f"{domain}-attack", remove_revoked_deprecated=True)
    return format_objects(techniques, include_description=include_description, domain=domain)


#####################################################################
# Mitigation functions
#####################################################################

@mcp.tool()
async def get_techniques_mitigated_by_mitigation(mitigation_stix_id: str, domain: str = "enterprise", include_description: bool = False) -> str:
    """Get techniques mitigated by mitigation

    Args:
        mitigation_stix_id: Mitigation STIX ID to check what techniques are mitigated by it
        domain: Domain name ('enterprise', 'mobile', or 'ics')
        include_description: Whether to include description in the output (default is False)
    """
    attack_data = get_attack_data(domain)
    techniques = attack_data.get_techniques_mitigated_by_mitigation(mitigation_stix_id)
    return format_objects(techniques, include_description=include_description, domain=domain)


@mcp.tool()
async def get_mitigations_mitigating_technique(technique_stix_id: str, domain: str = "enterprise", include_description: bool = False) -> str:
    """Get mitigations mitigating technique

    Args:
        technique_stix_id: Technique STIX ID to what mitigations are mitigating this technique
        domain: Domain name ('enterprise', 'mobile', or 'ics')
        include_description: Whether to include description in the output (default is False)
    """
    attack_data = get_attack_data(domain)
    mitigations = attack_data.get_mitigations_mitigating_technique(technique_stix_id)
    return format_objects(mitigations, include_description=include_description, domain=domain)


#####################################################################
# Data component and detection functions
#####################################################################

@mcp.tool()
async def get_datacomponents_detecting_technique(technique_stix_id: str, domain: str = "enterprise", include_description: bool = False) -> str:
    """Get datacomponents that detect the given technique

    Args:
        technique_stix_id: Technique STIX ID to check what datacomponents detect it
        domain: Domain name ('enterprise', 'mobile', or 'ics')
        include_description: Whether to include description in the output (default is False)
    """
    attack_data = get_attack_data(domain)
    datacomponents = attack_data.get_datacomponents_detecting_technique(technique_stix_id)
    
    # Special handling for datacomponents which need datasource name
    formatted_results = []
    
    for item in datacomponents:
        datacomponent = item["object"]
        datasource = attack_data.get_object_by_stix_id(datacomponent.x_mitre_data_source_ref)
        
        result = (
            f"Name Data Source: {datasource.name}\n"
            f"Name Data Component: {datacomponent.name}\n"
            f"ID: {attack_data.get_attack_id(datasource.id)}\n"
            f"STIX ID: {datasource.id}"
        )
        
        if include_description and hasattr(datacomponent, 'description'):
            result += f"\nDescription: {datacomponent.description}"
        
        formatted_results.append(result)
    
    return "\n---\n".join(formatted_results)


@mcp.tool()
async def get_techniques_detected_by_datacomponent(datacomponent_stix_id: str, domain: str = "enterprise", include_description: bool = False) -> str:
    """Get techniques detected by a datacomponent

    Args:
        datacomponent_stix_id: Datacomponent STIX ID to check what techniques it detects
        domain: Domain name ('enterprise', 'mobile', or 'ics')
        include_description: Whether to include description in the output (default is False)
    """
    attack_data = get_attack_data(domain)
    techniques = attack_data.get_techniques_detected_by_datacomponent(datacomponent_stix_id)
    return format_objects(techniques, include_description=include_description, domain=domain)

@mcp.tool()
async def get_procedure_examples_by_technique(technique_stix_id: str, domain: str = "enterprise", include_description: bool = False) -> str:
    """Get procedure examples by technique STIX ID (shows how groups use a technique)

    Args:
        technique_stix_id: Technique STIX ID to check how they are used and in what procedure
        domain: Domain name ('enterprise', 'mobile', or 'ics')
        include_description: Whether to include description in the output (default is False)
    """
    attack_data = get_attack_data(domain)
    procedure_examples = attack_data.get_procedure_examples_by_technique(technique_stix_id)
    return format_objects(procedure_examples, include_description=include_description, domain=domain)

@mcp.tool()
async def get_assets_targeted_by_technique(technique_stix_id: str, domain: str = "ics", include_description: bool = False) -> str:
    """Get assets targeted by technique STIX ID (shows how assets are targeted by technique), only pertains to ICS domain

    Args:
        technique_stix_id: Technique STIX ID to check what assets are targeted by it
        domain: Domain name ('ics')
        include_description: Whether to include description in the output (default is False)
    """
    attack_data = get_attack_data(domain)
    assets = attack_data.get_assets_targeted_by_technique(technique_stix_id)
    return format_objects(assets, include_description=include_description, domain=domain)

@mcp.tool()
async def get_campaigns_by_alias(alias: str, domain: str = "enterprise", include_description: bool = False) -> str:
    """Get campaigns by their alias

    Args:
        alias: Alias to find associated campaigns for
        domain: Domain name ('enterprise', 'mobile', or 'ics')
        include_description: Whether to include description in the output (default is False)
    """
    attack_data = get_attack_data(domain)
    campaigns = attack_data.get_campaigns_by_alias(alias)
    return format_objects(campaigns, include_description=include_description, domain=domain)

@mcp.tool()
async def get_objects_by_type(stix_type: str, domain: str = "enterprise", include_description: bool = False) -> str:
    """Get objects by STIX type

    Args:
        stix_type: TheSTIX object type (must be 'attack-pattern', 'malware', 'tool', 'intrusion-set',
            'campaign', 'course-of-action', 'x-mitre-matrix', 'x-mitre-tactic',
            'x-mitre-data-source', 'x-mitre-data-component', or 'x-mitre-asset')
        domain: Domain name ('enterprise', 'mobile', or 'ics')
        include_description: Whether to include description in the output (default is False)
    """
    attack_data = get_attack_data(domain)
    objects = attack_data.get_objects_by_type(stix_type, remove_revoked_deprecated=True)
    return format_objects(objects, include_description=include_description, domain=domain)


@mcp.tool()
async def get_tactics_by_matrix(matrix_stix_id: str, domain: str = "enterprise", include_description: bool = False) -> str:
    """Get tactics by matrix

    Args:
        matrix_stix_id: Matrix STIX ID to find associated tactics for
        domain: Domain name ('enterprise', 'mobile', or 'ics')
        include_description: Whether to include description in the output (default is False)
    """
    attack_data = get_attack_data(domain)
    tactics = attack_data.get_tactics_by_matrix(matrix_stix_id)
    return format_objects(tactics, include_description=include_description, domain=domain)


@mcp.tool()
async def get_tactics_by_technique(technique_stix_id: str, domain: str = "enterprise", include_description: bool = False) -> str:
    """Get tactics associated with a technique

    Args:
        technique_stix_id: Technique STIX ID to find associated tactics for
        domain: Domain name ('enterprise', 'mobile', or 'ics')
        include_description: Whether to include description in the output (default is False)
    """
    attack_data = get_attack_data(domain)
    tactics = attack_data.get_tactics_by_technique(technique_stix_id)
    return format_objects(tactics, include_description=include_description, domain=domain)


@mcp.tool()
async def get_procedure_examples_by_tactic(tactic: str, domain: str = "enterprise", include_description: bool = False) -> str:
    """Get procedure examples by tactic (shows how groups use techniques in this tactic)

    Args:
        tactic: Tactic name to check procedure examples for
        domain: Domain name ('enterprise', 'mobile', or 'ics')
        include_description: Whether to include description in the output (default is False)
    """
    attack_data = get_attack_data(domain)
    procedure_examples = attack_data.get_procedure_examples_by_tactic(tactic)
    return format_objects(procedure_examples, include_description=include_description, domain=domain)


@mcp.tool()
async def get_techniques_targeting_asset(asset_stix_id: str, domain: str = "ics", include_description: bool = False) -> str:
    """Get techniques targeting a specific asset (ICS domain only)

    Args:
        asset_stix_id: Asset STIX ID to find techniques targeting it
        domain: Domain name ('ics')
        include_description: Whether to include description in the output (default is False)
    """
    attack_data = get_attack_data(domain)
    techniques = attack_data.get_techniques_targeting_asset(asset_stix_id)
    return format_objects(techniques, include_description=include_description, domain=domain)


@mcp.tool()
async def get_objects_created_after(timestamp: str, domain: str = "enterprise", include_description: bool = False) -> str:
    """Get objects created after a specific timestamp

    Args:
        timestamp: ISO format timestamp string (e.g., '2020-01-01T00:00:00Z')
        domain: Domain name ('enterprise', 'mobile', or 'ics')
        include_description: Whether to include description in the output (default is False)
    """
    attack_data = get_attack_data(domain)
    objects = attack_data.get_objects_created_after(timestamp)
    return format_objects(objects, include_description=include_description, domain=domain)


@mcp.tool()
async def get_objects_modified_after(timestamp: str, domain: str = "enterprise", include_description: bool = False) -> str:
    """Get objects modified after a specific timestamp

    Args:
        timestamp: ISO format timestamp string (e.g., '2020-01-01T00:00:00Z')
        domain: Domain name ('enterprise', 'mobile', or 'ics')
        include_description: Whether to include description in the output (default is False)
    """
    attack_data = get_attack_data(domain)
    objects = attack_data.get_objects_modified_after(timestamp)
    return format_objects(objects, include_description=include_description, domain=domain)


@mcp.tool()
async def get_revoked_techniques(domain: str = "enterprise", include_description: bool = False) -> str:
    """Get all revoked techniques in the MITRE ATT&CK framework

    Args:
        domain: Domain name ('enterprise', 'mobile', or 'ics')
        include_description: Whether to include description in the output (default is False)
    """
    attack_data = get_attack_data(domain)
    techniques = attack_data.get_revoked_techniques()
    return format_objects(techniques, include_description=include_description, domain=domain)


#####################################################################
# Layer generation functions
#####################################################################

@mcp.tool()
async def generate_layer(attack_id: str, score: int, domain: str = "enterprise") -> str:
    """Generate an ATT&CK navigator layer in JSON format based on a matching ATT&CK ID value

    Args:
        attack_id: ATT&CK ID to generate ATT&CK navigator layer for. Valid match values are single ATT&CK ID's for group (GXXX), mitigation (MXXX), software (SXXX), and data component objects (DXXX) within the selected ATT&CK data. NEVER directly input a technique (TXXX). If an invalid match happens, or if multiple ATT&CK ID's are provided, present the user with an error message.
        score: Score to assign to each technique in the layer
        domain: Domain name ('enterprise', 'mobile', or 'ics')
    """
    try:
        # Validate input parameters
        valid_domains = ['enterprise', 'mobile', 'ics']
        
        if domain not in valid_domains:
            raise ValueError(f"Invalid domain: '{domain}'. Must be one of: {', '.join(valid_domains)}")
            
        if not attack_id or not isinstance(attack_id, str):
            raise ValueError("match must be a non-empty string")
            
        # Validate score is an integer
        if not isinstance(score, int):
            raise ValueError("score must be an integer")
            
        # Validate match format
        if not re.match(r'^[GMSD]\d+$', attack_id):
            raise ValueError("match must be a valid ATT&CK ID format (GXXX, MXXX, SXXX, or DXXX)")
            
        # Use the data path from arguments
        data_path = args.data_path
        
        # Domain key is used in the filename format
        domain_key = f"{domain}-attack"
        stix_path = os.path.join(data_path, "v" + release_info.LATEST_VERSION, f"{domain_key}.json")
        
        # Make sure the STIX file exists
        if not os.path.exists(stix_path):
            raise FileNotFoundError(f"STIX data file '{domain_key}.json' not found in data path '{data_path}'. Please ensure the data has been downloaded.")
        
        handle = UsageLayerGenerator(source='local', domain=domain, resource=stix_path)
        layer = handle.generate_layer(match=attack_id)
        
        if not layer or not layer.layer or not layer.layer.techniques:
            return f"No techniques found for '{attack_id}' in the '{domain}' domain."
        
        # Filter the techniques where score = 0
        layer.layer.techniques = [t for t in layer.layer.techniques if t.score > 0]
        
        # Apply score to the techniques
        for t in layer.layer.techniques:
            t.score = score

        return json.dumps(layer.to_dict())
        
    except ValueError as ve:
        return f"Validation error: {str(ve)}"
    except FileNotFoundError as fe:
        return f"File error: {str(fe)}"
    except KeyError as ke:
        return f"Data error: {str(ke)}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"


@mcp.tool()
async def get_layer_metadata(domain='enterprise') -> str:
    """
    Always call this tool whenever a prompt requires the generation of a MITRE ATT&CK Navigator Layer,
    such as the generate_layer tool. Always insert this metadata in the generated layer.
    
    Args:
        domain (str, optional): The ATT&CK domain ('enterprise', 'mobile', or 'ics'). Defaults to 'enterprise'.
    
    Returns:
        str: JSON string containing the appropriate layer metadata
    """
    # Base metadata template
    base_metadata = {
        "name": "layer",
        "versions": {
            "attack": "16",
            "navigator": "5.1.0",
            "layer": "4.5"
        },
        "description": "",
        "sorting": 0,
        "layout": {
            "layout": "side",
            "aggregateFunction": "average",
            "expandedSubtechniques": "none"
        },
        "techniques": [],
        "gradient": {
            "colors": [
                "#ff6666ff",
                "#ffe766ff",
                "#8ec843ff"
            ],
            "minValue": 0,
            "maxValue": 100
        },
        "legendItems": [],
        "metadata": [],
        "links": [],
        "tacticRowBackground": "#dddddd",
    }
    
    # Domain-specific configurations
    domain_configs = {
        'enterprise': {
            "domain": "enterprise-attack",
            "filters": {
                "platforms": [
                    "Windows", "Linux", "macOS", "Network", "PRE",
                    "Containers", "IaaS", "SaaS", "Office Suite", "Identity Provider"
                ]
            }
        },
        'mobile': {
            "domain": "mobile-attack",
            "filters": {
                "platforms": ["Android", "iOS"]
            }
        },
        'ics': {
            "domain": "ics-attack",
            "filters": {
                "platforms": ["None"]
            }
        }
    }
    
    # Validate domain and default to enterprise if invalid
    domain = domain.lower()
    if domain not in domain_configs:
        domain = 'enterprise'
    
    # Add domain-specific configuration to base metadata
    metadata = base_metadata.copy()
    metadata.update(domain_configs[domain])
    
    return json.dumps(metadata)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("data_path")
    
    args = parser.parse_args()
  
    # Create the data directory if it doesn't exist
    if not os.path.exists(args.data_path):
        os.makedirs(args.data_path)
    
    # Check if data files exist in the specified path
    data_exists = all(os.path.exists(os.path.join(args.data_path, "v" + release_info.LATEST_VERSION, f"{domain}-attack.json")) 
                    for domain in ["enterprise", "mobile", "ics"])
    
    # Download data if requested or if files don't exist
    if  not data_exists:
        download_stix_data(args.data_path)
    
    # Load STIX data from the specified path
    loaded_domains = load_stix_data(args.data_path)
    
    if not loaded_domains:
        exit(1)
    
    mcp.run(transport='stdio')
