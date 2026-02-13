"""
Entity extraction utilities for extracting users, IPs, hostnames, etc. from query results (LangGraph version).
"""
import re
from typing import Dict, List, Optional, Set, Tuple


# Field name patterns for different entity types
# Ordered by priority (higher priority fields come first)
USER_FIELD_PATTERNS = [
    r'^user$',  # Exact match 'user' has highest priority
    r'^username$',
    r'^account$',
    r'^accountname$',
    r'^targetuser$',
    r'^suspectuser$',
    r'^srcuser$',
    r'^dstuser$',
    r'.*user.*',  # Any field containing 'user'
]

IP_FIELD_PATTERNS = [
    r'^srcip$',  # Source IP has highest priority
    r'^dstip$',  # Destination IP
    r'^ip$',
    r'^sourceip$',
    r'^destinationip$',
    r'^src_ip$',
    r'^dst_ip$',
    r'.*ip.*',  # Any field containing 'ip'
]

HOSTNAME_FIELD_PATTERNS = [
    r'^hostname$',
    r'^host$',
    r'^system$',
    r'^machine$',
    r'^computername$',
    r'^device$',
    r'.*host.*',
]

DOMAIN_FIELD_PATTERNS = [
    r'^domain$',
    r'^fqdn$',
    r'^domainname$',
    r'.*domain.*',
]

FILE_PATH_FIELD_PATTERNS = [
    r'^filepath$',
    r'^filename$',
    r'^file$',
    r'^path$',
    r'.*file.*',
]


def calculate_field_priority(field_name: str, patterns: List[str]) -> Optional[int]:
    """
    Calculate priority score for a field based on pattern matching.
    Lower number = higher priority.
    
    Args:
        field_name: Field name to check
        patterns: List of regex patterns ordered by priority
        
    Returns:
        Priority index (0 = highest priority) or None if no match
    """
    field_lower = field_name.lower()
    for idx, pattern in enumerate(patterns):
        if re.match(pattern, field_lower):
            return idx
    return None


def is_valid_ip(value: str) -> bool:
    """Check if a string is a valid IP address."""
    if not value or not isinstance(value, str):
        return False
    
    # IPv4 pattern
    ipv4_pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
    if re.match(ipv4_pattern, value):
        parts = value.split('.')
        return all(0 <= int(p) <= 255 for p in parts if p.isdigit())
    
    # IPv6 pattern (simplified)
    ipv6_pattern = r'^([0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}$|^::1$|^::$'
    if re.match(ipv6_pattern, value):
        return True
    
    return False


def is_valid_domain(value: str) -> bool:
    """Check if a string looks like a domain name."""
    if not value or not isinstance(value, str):
        return False
    
    # Basic domain pattern
    domain_pattern = r'^([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$'
    return bool(re.match(domain_pattern, value))


def extract_entities_from_results(
    execution_results: List[Dict[str, any]],
    entity_types: Optional[List[str]] = None
) -> Dict[str, Dict[str, any]]:
    """
    Extract entities (users, IPs, hostnames, etc.) from query execution results.
    
    Args:
        execution_results: List of execution result dictionaries, each containing:
            - 'results': List of result dictionaries
            - 'result_count': Number of results
            - 'query': Query string
        entity_types: Optional list of entity types to extract. If None, extracts all.
                     Valid types: 'user', 'ip', 'hostname', 'domain', 'filepath'
        
    Returns:
        Dictionary mapping entity type to entity data:
        {
            'user': {
                'values': ['user1', 'user2'],
                'fields': ['user', 'username'],
                'field_priorities': {'user': 0, 'username': 1},
                'confidence': 0.95
            },
            ...
        }
    """
    if not execution_results:
        return {}
    
    # Filter to only results with data
    results_with_data = [
        exec_res for exec_res in execution_results
        if exec_res.get('result_count', 0) > 0 
        and exec_res.get('results')
        and 'error' not in exec_res
    ]
    
    if not results_with_data:
        return {}
    
    # Collect all result dictionaries
    all_results = []
    for exec_res in results_with_data:
        all_results.extend(exec_res.get('results', []))
    
    if not all_results:
        return {}
    
    # Get all field names from results
    all_fields = set()
    for result in all_results:
        if isinstance(result, dict):
            all_fields.update(result.keys())
    
    # Extract entities by type
    extracted_entities = {}
    
    if entity_types is None:
        entity_types = ['user', 'ip', 'hostname', 'domain', 'filepath']
    
    # Extract users
    if 'user' in entity_types:
        user_data = _extract_user_entities(all_results, all_fields)
        if user_data['values']:
            extracted_entities['user'] = user_data
    
    # Extract IPs
    if 'ip' in entity_types:
        ip_data = _extract_ip_entities(all_results, all_fields)
        if ip_data['values']:
            extracted_entities['ip'] = ip_data
    
    # Extract hostnames
    if 'hostname' in entity_types:
        hostname_data = _extract_hostname_entities(all_results, all_fields)
        if hostname_data['values']:
            extracted_entities['hostname'] = hostname_data
    
    # Extract domains
    if 'domain' in entity_types:
        domain_data = _extract_domain_entities(all_results, all_fields)
        if domain_data['values']:
            extracted_entities['domain'] = domain_data
    
    # Extract file paths
    if 'filepath' in entity_types:
        filepath_data = _extract_filepath_entities(all_results, all_fields)
        if filepath_data['values']:
            extracted_entities['filepath'] = filepath_data
    
    return extracted_entities


def _extract_user_entities(results: List[Dict], fields: Set[str]) -> Dict[str, any]:
    """Extract user entities from results."""
    user_values = set()
    user_fields = []
    field_priorities = {}
    
    # Find matching fields
    for field in fields:
        priority = calculate_field_priority(field, USER_FIELD_PATTERNS)
        if priority is not None:
            user_fields.append(field)
            field_priorities[field] = priority
    
    # Sort fields by priority (lower priority number = higher priority)
    user_fields.sort(key=lambda f: field_priorities.get(f, 999))
    
    # Extract values from results, prioritizing higher priority fields
    for field in user_fields:
        for result in results:
            value = result.get(field)
            if value and isinstance(value, (str, int)):
                value_str = str(value).strip()
                if value_str and value_str not in ['null', 'none', '']:
                    user_values.add(value_str)
    
    # Calculate confidence based on field priority
    confidence = 0.9 if user_fields else 0.0
    if user_fields and field_priorities.get(user_fields[0], 999) == 0:
        confidence = 0.95  # Highest confidence for exact 'user' field
    
    return {
        'values': sorted(list(user_values)),
        'fields': user_fields,
        'field_priorities': field_priorities,
        'confidence': confidence
    }


def _extract_ip_entities(results: List[Dict], fields: Set[str]) -> Dict[str, any]:
    """Extract IP entities from results."""
    ip_values = set()
    ip_fields = []
    field_priorities = {}
    
    # Find matching fields
    for field in fields:
        priority = calculate_field_priority(field, IP_FIELD_PATTERNS)
        if priority is not None:
            ip_fields.append(field)
            field_priorities[field] = priority
    
    # Sort fields by priority
    ip_fields.sort(key=lambda f: field_priorities.get(f, 999))
    
    # Extract values and validate they're actually IPs
    for field in ip_fields:
        for result in results:
            value = result.get(field)
            if value and isinstance(value, (str, int)):
                value_str = str(value).strip()
                if value_str and is_valid_ip(value_str):
                    ip_values.add(value_str)
    
    # Calculate confidence
    confidence = 0.9 if ip_fields else 0.0
    if ip_fields and field_priorities.get(ip_fields[0], 999) == 0:
        confidence = 0.95  # Highest confidence for 'srcip' field
    
    return {
        'values': sorted(list(ip_values)),
        'fields': ip_fields,
        'field_priorities': field_priorities,
        'confidence': confidence
    }


def _extract_hostname_entities(results: List[Dict], fields: Set[str]) -> Dict[str, any]:
    """Extract hostname entities from results."""
    hostname_values = set()
    hostname_fields = []
    field_priorities = {}
    
    # Find matching fields
    for field in fields:
        priority = calculate_field_priority(field, HOSTNAME_FIELD_PATTERNS)
        if priority is not None:
            hostname_fields.append(field)
            field_priorities[field] = priority
    
    # Sort fields by priority
    hostname_fields.sort(key=lambda f: field_priorities.get(f, 999))
    
    # Extract values
    for field in hostname_fields:
        for result in results:
            value = result.get(field)
            if value and isinstance(value, (str, int)):
                value_str = str(value).strip()
                if value_str and value_str not in ['null', 'none', '']:
                    # Exclude IPs and domains
                    if not is_valid_ip(value_str) and not is_valid_domain(value_str):
                        hostname_values.add(value_str)
    
    confidence = 0.85 if hostname_fields else 0.0
    if hostname_fields and field_priorities.get(hostname_fields[0], 999) == 0:
        confidence = 0.9
    
    return {
        'values': sorted(list(hostname_values)),
        'fields': hostname_fields,
        'field_priorities': field_priorities,
        'confidence': confidence
    }


def _extract_domain_entities(results: List[Dict], fields: Set[str]) -> Dict[str, any]:
    """Extract domain entities from results."""
    domain_values = set()
    domain_fields = []
    field_priorities = {}
    
    # Find matching fields
    for field in fields:
        priority = calculate_field_priority(field, DOMAIN_FIELD_PATTERNS)
        if priority is not None:
            domain_fields.append(field)
            field_priorities[field] = priority
    
    # Sort fields by priority
    domain_fields.sort(key=lambda f: field_priorities.get(f, 999))
    
    # Extract values and validate they're domains
    for field in domain_fields:
        for result in results:
            value = result.get(field)
            if value and isinstance(value, str):
                value_str = value.strip()
                if value_str and is_valid_domain(value_str):
                    domain_values.add(value_str)
    
    confidence = 0.85 if domain_fields else 0.0
    
    return {
        'values': sorted(list(domain_values)),
        'fields': domain_fields,
        'field_priorities': field_priorities,
        'confidence': confidence
    }


def _extract_filepath_entities(results: List[Dict], fields: Set[str]) -> Dict[str, any]:
    """Extract file path entities from results."""
    filepath_values = set()
    filepath_fields = []
    field_priorities = {}
    
    # Find matching fields
    for field in fields:
        priority = calculate_field_priority(field, FILE_PATH_FIELD_PATTERNS)
        if priority is not None:
            filepath_fields.append(field)
            field_priorities[field] = priority
    
    # Sort fields by priority
    filepath_fields.sort(key=lambda f: field_priorities.get(f, 999))
    
    # Extract values (look for path-like strings)
    for field in filepath_fields:
        for result in results:
            value = result.get(field)
            if value and isinstance(value, str):
                value_str = value.strip()
                if value_str and ('/' in value_str or '\\' in value_str):
                    filepath_values.add(value_str)
    
    confidence = 0.8 if filepath_fields else 0.0
    
    return {
        'values': sorted(list(filepath_values)),
        'fields': filepath_fields,
        'field_priorities': field_priorities,
        'confidence': confidence
    }


def detect_aggregated_query(query: str) -> Optional[Dict[str, any]]:
    """
    Detect if a query uses aggregation functions and identify the entity field being aggregated.
    
    Args:
        query: DQL query string
        
    Returns:
        Dictionary with:
        - 'is_aggregated': bool
        - 'entity_field': str or None (the field being aggregated, e.g., 'user', 'srcip')
        - 'aggregation_type': str or None (e.g., 'distinct_count', 'count')
        Or None if not aggregated
    """
    query_lower = query.lower()
    
    # Patterns for aggregation functions that aggregate a specific field
    aggregation_patterns = [
        (r'select\s+distinct_count\s*\(\s*(\w+)\s*\)', 'distinct_count', 'user'),
        (r'select\s+count\s*\(\s*(\w+)\s*\)', 'count', 'user'),
        (r'select\s+count_if\s*\([^)]*\)', 'count_if', None),  # More complex, field extraction harder
    ]
    
    # Check for aggregation patterns
    for pattern, agg_type, default_field in aggregation_patterns:
        match = re.search(pattern, query_lower)
        if match:
            entity_field = match.group(1) if match.groups() else default_field
            return {
                'is_aggregated': True,
                'entity_field': entity_field,
                'aggregation_type': agg_type
            }
    
    # Check for count(*) or count without field
    if re.search(r'select\s+count\s*\(\s*\*\s*\)', query_lower):
        # Check if there's a groupby clause - if so, the groupby field is the entity
        groupby_match = re.search(r'groupby\s+(\w+)', query_lower)
        if groupby_match:
            return {
                'is_aggregated': True,
                'entity_field': groupby_match.group(1),
                'aggregation_type': 'count'
            }
        return {
            'is_aggregated': True,
            'entity_field': None,
            'aggregation_type': 'count'
        }
    
    return None


def has_only_count_fields(results: List[Dict]) -> bool:
    """
    Check if results contain only count fields (no actual entity values).
    
    Args:
        results: List of result dictionaries
        
    Returns:
        True if results only contain count fields, False otherwise
    """
    if not results:
        return False
    
    # Get all field names
    all_fields = set()
    for result in results:
        if isinstance(result, dict):
            all_fields.update(result.keys())
    
    # Check if all fields are count-related
    count_patterns = [
        r'count',
        r'distinct_count',
        r'sum',
        r'avg',
        r'max',
        r'min'
    ]
    
    non_count_fields = []
    for field in all_fields:
        field_lower = field.lower()
        is_count_field = any(re.search(pattern, field_lower) for pattern in count_patterns)
        if not is_count_field:
            non_count_fields.append(field)
    
    # If we have non-count fields, we have entity values
    return len(non_count_fields) == 0


def modify_query_to_fetch_entities(query: str, entity_field: str) -> str:
    """
    Modify an aggregated query to return actual entity values instead of counts.
    
    Args:
        query: Original aggregated query
        entity_field: Entity field to fetch (e.g., 'user', 'srcip')
        
    Returns:
        Modified query that returns entity values
    """
    query_lower = query.lower()
    modified_query = query
    
    # Check if query already has groupby
    has_groupby = 'groupby' in query_lower
    
    # Pattern to match SELECT clause
    select_pattern = r'select\s+[^|]+?(?=\s*\||$)'
    
    if has_groupby:
        # Query already has groupby - just ensure entity field is in groupby
        groupby_match = re.search(r'groupby\s+([^|]+?)(?=\s*\||$)', query_lower)
        if groupby_match:
            groupby_fields = groupby_match.group(1).strip()
            # Check if entity_field is already in groupby
            if entity_field.lower() not in groupby_fields.lower():
                # Add entity_field to groupby
                modified_query = re.sub(
                    r'groupby\s+([^|]+?)(?=\s*\||$)',
                    lambda m: f"groupby {m.group(1).strip()}, {entity_field}",
                    modified_query,
                    flags=re.IGNORECASE
                )
    else:
        # No groupby - remove SELECT clause and add groupby
        # Remove SELECT clause
        modified_query = re.sub(select_pattern, '', modified_query, flags=re.IGNORECASE)
        
        # Find where to insert groupby (before duration, limit, or at end)
        # Insert before first pipe after WHERE clause, or before duration/limit
        insert_patterns = [
            (r'(\|\s*duration\s+\d+[dwmyhms])', f'| groupby {entity_field} \\1'),
            (r'(\|\s*limit\s+\d+)', f'| groupby {entity_field} \\1'),
            (r'(\|\s*last)', f'| groupby {entity_field} \\1'),
        ]
        
        inserted = False
        for pattern, replacement in insert_patterns:
            if re.search(pattern, modified_query, re.IGNORECASE):
                modified_query = re.sub(pattern, replacement, modified_query, flags=re.IGNORECASE, count=1)
                inserted = True
                break
        
        if not inserted:
            # No duration/limit found - add groupby at the end
            # Find the last pipe or add before end
            modified_query = modified_query.rstrip()
            # Remove trailing pipe if present
            if modified_query.endswith('|'):
                modified_query = modified_query.rstrip('|').rstrip()
            # Add groupby
            modified_query = modified_query + f' | groupby {entity_field}'
    
    # Clean up any double spaces or pipes
    modified_query = re.sub(r'\s+', ' ', modified_query)
    modified_query = re.sub(r'\|\s*\|', '|', modified_query)
    modified_query = modified_query.strip()
    
    return modified_query


def extract_entities_from_queries(queries: List[str]) -> Dict[str, Dict[str, any]]:
    """
    Extract entity fields from query structures (e.g., groupby clauses, where clauses).
    
    Args:
        queries: List of DQL query strings
        
    Returns:
        Dictionary mapping entity type to entity data (similar to extract_entities_from_results)
        Note: This returns field names, not actual values (since queries don't have values)
    """
    if not queries:
        return {}
    
    extracted_entities = {}
    
    # Patterns to find entity fields in queries
    # Check groupby clauses
    groupby_pattern = r'groupby\s+([^|]+?)(?=\s*\||$)'
    # Check where clauses with entity fields
    where_patterns = [
        r'where\s+(\w+)\s*=',  # where user='value'
        r'where\s+(\w+)\s+in\s*\(',  # where user in (...)
        r'where\s+(\w+)\s+is\s+not\s+null',  # where user is not null
    ]
    # Check select clauses
    select_pattern = r'select\s+([^|]+?)(?=\s*\||$)'
    
    all_entity_fields = {
        'user': set(),
        'ip': set(),
        'hostname': set(),
        'domain': set(),
        'filepath': set()
    }
    
    for query in queries:
        query_lower = query.lower()
        
        # Extract from groupby
        groupby_match = re.search(groupby_pattern, query_lower)
        if groupby_match:
            groupby_fields = groupby_match.group(1).strip()
            # Split by comma and check each field
            for field in groupby_fields.split(','):
                field = field.strip()
                # Check which entity type this field belongs to
                for entity_type, patterns in [
                    ('user', USER_FIELD_PATTERNS),
                    ('ip', IP_FIELD_PATTERNS),
                    ('hostname', HOSTNAME_FIELD_PATTERNS),
                    ('domain', DOMAIN_FIELD_PATTERNS),
                    ('filepath', FILE_PATH_FIELD_PATTERNS)
                ]:
                    if any(re.match(pattern, field) for pattern in patterns):
                        all_entity_fields[entity_type].add(field)
                        break
        
        # Extract from where clauses
        for pattern in where_patterns:
            matches = re.finditer(pattern, query_lower)
            for match in matches:
                field = match.group(1).strip()
                # Check which entity type
                for entity_type, patterns in [
                    ('user', USER_FIELD_PATTERNS),
                    ('ip', IP_FIELD_PATTERNS),
                    ('hostname', HOSTNAME_FIELD_PATTERNS),
                    ('domain', DOMAIN_FIELD_PATTERNS),
                    ('filepath', FILE_PATH_FIELD_PATTERNS)
                ]:
                    if any(re.match(p, field) for p in patterns):
                        all_entity_fields[entity_type].add(field)
                        break
        
        # Extract from select clauses (non-aggregate fields)
        select_match = re.search(select_pattern, query_lower)
        if select_match:
            select_fields = select_match.group(1).strip()
            # Check if it's an aggregate function
            if not re.search(r'(distinct_count|count|sum|avg|max|min)\s*\(', select_fields.lower()):
                # Not aggregate, check fields
                for field in select_fields.split(','):
                    field = field.strip()
                    # Remove aliases (e.g., "user as username")
                    field = re.sub(r'\s+as\s+\w+', '', field, flags=re.IGNORECASE).strip()
                    for entity_type, patterns in [
                        ('user', USER_FIELD_PATTERNS),
                        ('ip', IP_FIELD_PATTERNS),
                        ('hostname', HOSTNAME_FIELD_PATTERNS),
                        ('domain', DOMAIN_FIELD_PATTERNS),
                        ('filepath', FILE_PATH_FIELD_PATTERNS)
                    ]:
                        if any(re.match(p, field) for p in patterns):
                            all_entity_fields[entity_type].add(field)
                            break
    
    # Build result structure
    for entity_type, fields in all_entity_fields.items():
        if fields:
            # Sort fields by priority
            field_list = sorted(list(fields))
            extracted_entities[entity_type] = {
                'values': [],  # No actual values from queries
                'fields': field_list,
                'field_priorities': {f: calculate_field_priority(f, USER_FIELD_PATTERNS if entity_type == 'user' else 
                                                                 IP_FIELD_PATTERNS if entity_type == 'ip' else
                                                                 HOSTNAME_FIELD_PATTERNS if entity_type == 'hostname' else
                                                                 DOMAIN_FIELD_PATTERNS if entity_type == 'domain' else
                                                                 FILE_PATH_FIELD_PATTERNS) for f in field_list},
                'confidence': 0.7,  # Lower confidence since we don't have actual values
                'source': 'query_structure'  # Indicate these came from query structure
            }
    
    return extracted_entities

