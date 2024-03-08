from N2G import drawio_diagram
import yaml
from collections import defaultdict
import argparse
import os

def assign_tiers(nodes, links):
    # Initialize all nodes with no tier (-1) or with their specified tier or graph-level if present
    node_tiers = {}
    for node in nodes:
        if 'labels' in nodes[node]:
            graph_level = nodes[node]['labels'].get('graph-level', -1)
            tier = nodes[node]['labels'].get('tier', -1)
            # Prioritize graph-level over tier if graph-level is defined
            node_tiers[node] = graph_level if graph_level != -1 else tier
        else:
            node_tiers[node] = -1

    # Initialize the connections dictionary
    connections = {node: {'upstream': set(), 'downstream': set()} for node in nodes}
    for link in links:
        source, target = link['source'], link['target']
        connections[source]['downstream'].add(target)
        connections[target]['upstream'].add(source)

    # Helper function to assign tier by recursively checking connections
    def set_tier(node, current_tier):
        if node_tiers[node] != -1 and node_tiers[node] < current_tier:
            # Skip setting tier if it is manually set and higher than the current tier
            return
        node_tiers[node] = max(node_tiers[node], current_tier)
        for downstream_node in connections[node]['downstream']:
            set_tier(downstream_node, current_tier + 1)

    # Start by setting the tier of nodes with no upstream connections or with a manually set tier
    for node in nodes:
        if node_tiers[node] == -1 and not connections[node]['upstream']:
            set_tier(node, 0)
        elif node_tiers[node] != -1:
            # Manually set the tier for nodes with a specified tier
            set_tier(node, node_tiers[node])

    # Sort nodes by tier and then by name to maintain consistent ordering
    sorted_nodes = sorted(node_tiers, key=lambda n: (node_tiers[n], n))
    return sorted_nodes, node_tiers, connections

def adjust_overlapping_nodes(nodes_by_tier, positions, offset_amount, orientation='vertical'):
    """Apply a symmetric offset to overlapping nodes within each tier to separate them vertically or horizontally.
    
    Args:
        nodes_by_tier (dict): Nodes organized by their tier.
        positions (dict): Current positions of each node.
        offset_amount (int): Amount to offset overlapping nodes in one direction; the other node will be offset oppositely.
        orientation (str): Orientation of the layout, 'vertical' or 'horizontal'.
    """
    for tier, nodes in nodes_by_tier.items():
        if orientation == 'vertical':
            # For vertical orientation, sort by x position
            sorted_nodes = sorted(nodes, key=lambda node: positions[node][0])
        else:
            # For horizontal orientation, sort by y position
            sorted_nodes = sorted(nodes, key=lambda node: positions[node][1])

        for i in range(len(sorted_nodes) - 1):
            node = sorted_nodes[i]
            next_node = sorted_nodes[i + 1]

            if orientation == 'vertical':
                # Check if nodes are at the same x position (indicating a potential overlap)
                if positions[node][0] == positions[next_node][0]:
                    # Apply symmetric offset in the x direction
                    positions[node] = (positions[node][0] - offset_amount, positions[node][1])
                    positions[next_node] = (positions[next_node][0] + offset_amount, positions[next_node][1])
            else:
                # Check if nodes are at the same y position (indicating a potential overlap)
                if positions[node][1] == positions[next_node][1]:
                    # Apply symmetric offset in the y direction
                    positions[node] = (positions[node][0], positions[node][1] - offset_amount)
                    positions[next_node] = (positions[next_node][0], positions[next_node][1] + offset_amount)

def calculate_positions(sorted_nodes, links, node_tiers, connections,  orientation='vertical'):
    x_start, y_start = 100, 100
    padding_x, padding_y = 200, 200
    positions = {}

    # Build adjacency list from the links for direct connections
    adjacency = defaultdict(set)
    for link in links:
        src, dst = link['source'], link['target']
        adjacency[src].add(dst)
        adjacency[dst].add(src)

    # Function to prioritize placement of nodes based on connectivity
    def prioritize_node_placement(nodes, adjacency):
        # Adjust the calculation of connection counts to consider only connections to nodes within the 'nodes' list
        connection_counts = {}
        for node in nodes:
            # Count connections that are both in the adjacency list and in the 'nodes' list
            connected_nodes = adjacency[node] & set(nodes)
            connection_counts[node] = len(connected_nodes)

        # Separate nodes based on their number of connections within the subset
        many_connections_nodes = [node for node, count in connection_counts.items() if count > 1]
        single_connection_nodes = [node for node, count in connection_counts.items() if count == 1]

        # Identify nodes not classified as many or single connection nodes (e.g., leaf3)
        unclassified_nodes = set(nodes) - set(many_connections_nodes) - set(single_connection_nodes)

        # If no nodes fit into many or single connection categories, default to sorting by name
        if not many_connections_nodes and not single_connection_nodes:
            ordered_nodes = sorted(nodes, key=lambda x: x)
        else:
            # Start with nodes having many connections, sorted by name
            ordered_nodes = sorted(many_connections_nodes, key=lambda x: x)

        # Function to find the index for a single connection node
        def find_best_insertion_index(single_node, ordered_nodes, adjacency):
            # Determine the connected node for the single_node
            connected_node = next(iter([n for n in adjacency[single_node] if n in ordered_nodes]), None)

            if connected_node:
                # Get the index of the connected node in the ordered list
                connected_node_index = ordered_nodes.index(connected_node)

                # Determine placement preference based on existing connections
                # Check if the connected node has connections that dictate the placement of the single_node
                before_connected = any(adjacency[connected_node] & set(ordered_nodes[:connected_node_index]))
                after_connected = any(adjacency[connected_node] & set(ordered_nodes[connected_node_index + 1:]))

                if before_connected and not after_connected:
                    # If there are connections before but not after, insert after the connected node
                    return connected_node_index + 1
                elif not before_connected and after_connected:
                    # If there are connections after but not before, insert before the connected node
                    return connected_node_index
                elif not before_connected and not after_connected:
                    # If the connected node is not connected to other nodes in the list, prioritize based on name
                    if single_node < connected_node:
                        return connected_node_index
                    else:
                        return connected_node_index + 1
                else:
                    # If both sides have connections, place based on additional logic or name
                    if single_node < connected_node:
                        return connected_node_index
                    else:
                        return connected_node_index + 1
            else:
                # If no directly connected node is in the ordered list, default to appending
                return len(ordered_nodes)

        # For nodes with single connections, find the best insertion index based on adjacency
        for single_node in sorted(single_connection_nodes, key=lambda x: x):
            index = find_best_insertion_index(single_node, ordered_nodes, adjacency)
            ordered_nodes.insert(index, single_node)

        # Append unclassified nodes (sorted by name for consistency) at the end or integrate based on specific logic
        ordered_nodes.extend(sorted(unclassified_nodes, key=lambda x: x))

        return ordered_nodes

    # Initialize nodes by tier and reorder within each tier based on connectivity
    nodes_by_tier = defaultdict(list)
    for node in sorted_nodes:
        tier = node_tiers[node]
        nodes_by_tier[tier].append(node)

    # Adjusted part for horizontal topology
    for tier, tier_nodes in nodes_by_tier.items():
        ordered_tier_nodes = prioritize_node_placement(tier_nodes, adjacency)

        if orientation == 'vertical':
            x_pos = x_start
            for node in ordered_tier_nodes:
                positions[node] = (x_pos, y_start + tier * padding_y)
                x_pos += padding_x

        elif orientation == 'horizontal':
            y_pos = y_start
            for node in ordered_tier_nodes:
                positions[node] = (x_start + tier * padding_x, y_pos)
                y_pos += padding_y
    # Center alignment logic for both orientations
    if orientation == 'vertical':
        tier_centers = {tier: (min(positions[node][0] for node in nodes) + max(positions[node][0] for node in nodes)) / 2 for tier, nodes in nodes_by_tier.items()}
        widest_tier_center = tier_centers[max(nodes_by_tier.keys(), key=lambda t: len(nodes_by_tier[t]))]

        for tier, nodes in nodes_by_tier.items():
            tier_center = tier_centers[tier]
            offset = widest_tier_center - tier_center
            for node in nodes:
                positions[node] = (positions[node][0] + offset, positions[node][1])
        adjust_overlapping_nodes(nodes_by_tier, positions, offset_amount=250, orientation='vertical')

    elif orientation == 'horizontal':
        # Adjust y_start based on connections for nodes that have connections to higher tiers
        y_pos = y_start
        nodes_adjustment = defaultdict(int)  # Dictionary to hold the adjustment needed for y positions

        for node in sorted_nodes:
            if node in nodes_by_tier[node_tiers[node]]:
                downstream_nodes = connections[node]['downstream']
                max_tier_downstream = max([node_tiers[n] for n in downstream_nodes if n in node_tiers] + [node_tiers[node]])
                # Calculate the adjustment needed based on the difference in tiers
                tier_difference = max_tier_downstream - node_tiers[node]
                if tier_difference > 0:
                    nodes_adjustment[node] = tier_difference * padding_y // 2  # Modify the divisor as needed for visual appearance

        for tier, tier_nodes in nodes_by_tier.items():
            for node in tier_nodes:
                positions[node] = (x_start + tier * padding_x, y_pos + nodes_adjustment[node])
                y_pos += padding_y

        # Apply center alignment adjustments for the horizontal layout
        tier_centers = {tier: (min(positions[node][1] for node in nodes) + max(positions[node][1] for node in nodes)) / 2 for tier, nodes in nodes_by_tier.items()}
        tallest_tier_center = tier_centers[max(nodes_by_tier.keys(), key=lambda t: len(nodes_by_tier[t]))]

        for tier, nodes in nodes_by_tier.items():
            tier_center = tier_centers[tier]
            offset = tallest_tier_center - tier_center
            for node in nodes:
                # Apply the calculated offset to center the nodes vertically within their tier
                positions[node] = (positions[node][0], positions[node][1] + offset)
        adjust_overlapping_nodes(nodes_by_tier, positions, offset_amount=250, orientation='horizontal')

    return positions

def create_link_style(base_style, positions, source, target, source_tier, target_tier, offset_index, total_links, orientation='vertical'):
    source_x, source_y = positions[source]
    target_x, target_y = positions[target]
    same_graph_level = source_tier == target_tier

    if orientation == 'vertical':
        if total_links == 1 and same_graph_level and source_x < target_x:
            # For same graph-level from left to right
            entryX, exitX = 0, 1
            entryY = exitY = 0.5
        elif total_links == 1 and same_graph_level:
            # For same graph-level from right to left
            entryX, exitX = 0, 1
            entryY = exitY = 0.5
        else:
            entryX = exitX = 0.5  # Default for vertical links
            if total_links > 1:
                # Adjust for multiple links
                step = 1.0 / total_links
                entryY = exitY = step * (offset_index + 1) - step / 2
            else:
                entryY = 0 if source_y < target_y else 1
                exitY = 1 if source_y < target_y else 0

    elif orientation == 'horizontal':
        if total_links == 1 and same_graph_level and source_y < target_y:
            # For same graph-level from top to bottom
            entryY, exitY = 0, 1
            entryX = exitX = 0.5
        elif total_links == 1 and same_graph_level:
            # For same graph-level from bottom to top
            entryY, exitY = 0, 1
            entryX = exitX = 0.5
        else:
            entryY = exitY = 0.5  # Default for horizontal links
            if total_links > 1:
                # Adjust for multiple links
                step = 1.0 / total_links
                entryX = exitX = step * (offset_index + 1) - step / 2
            else:
                entryX = 0 if source_x < target_x else 1
                exitX = 1 if source_x < target_x else 0

    updated_style = f"{base_style}entryY={entryY};exitY={exitY};entryX={entryX};exitX={exitX};"
    return updated_style

def add_nodes_and_links(diagram, nodes, positions, links, node_tiers):
    # Add nodes to the diagram with their calculated positions

    # Base style for fixed size and label positioning
    base_style = "shape=image;imageAlign=center;imageVerticalAlign=middle;labelPosition=left;align=right;verticalLabelPosition=top;spacingLeft=0;verticalAlign=bottom;spacingTop=0;spacing=0;"
    link_style = "endArrow=none;jumpStyle=gap;" 
    src_label_style = "verticalLabelPosition=bottom;verticalAlign=top;align=left;spacingLeft=1;spacingTop=1;spacingBottom=0;"
    trgt_label_style = "verticalLabelPosition=top;verticalAlign=bottom;align=left;spacingLeft=1;spacingTop=1;spacingBottom=0;" 

    # Define custom styles for each group with a placeholder for the image
    custom_styles = {
        "default": base_style + "image=data:image/png,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;",
        "spine": base_style + "image=data:image/png,iVBORw0KGgoAAAANSUhEUgAAAFgAAABYCAYAAABxlTA0AAAAAXNSR0IArs4c6QAAAARnQU1BAACxjwv8YQUAAAAJcEhZcwAAFxEAABcRAcom8z8AAAikSURBVHhe7ZwJbBRVGMe3pUBrASkUlVMpV6EUQSlCCqhEjbYiIQEUETFyVEAr3hDwquCFVE2EYoTWCBTk8KgmiBfGqDEoRbkE5JByWW9UtJTC5/d/MwPD8na7OzOvu4vvS35pd3bezPS337735r039flSskijiKZZf2nBKtGCFaMFK0YLVowWrBgtWDFasGK0YMVowYrRghUTlYIbX8IX1lv+XqwRVYKb9SFfYiYlpPYlX1IP+T6xRtQIhlxfF2rf4wbasHE7jc57lF+nyfeVgYyPS+cyncWHJI4n26+uiQrBpty0jFzavfcAIU6cOEE33jY1NMnnXkoJLfrSkFH308hx0ykzeyT5knvK961rIi7YytxuOSz3oJBrxQlm+JiHapfcqCc1aXcFVR2tFuUK5y7hMh3l+9Y1ERV8WuaeLtcKSB5Rm2QW3Ljt5VT582+izKw5xbx/J/m+dU3EBFtyOXP3VBwSYhBHzSw8Wm38tCKoZC3YjwDVwosvv04LFr0tft+6fQ/d9eBs8TsCdXLA6kILtgG5cWa1UHFK7qLlq1lKGyoqXiVe7913iHz1utJtEx8TrxGoLqQNnxZsg7tQPfuNoH0HK4UMxOIV75GvQQZLuYhKSt8V2yr2/0gNL8jmbe1ofP5Msc2K2yc/Tr6G3U8dUwu2kdCVcoffLUQgFiNzIfeci1lKOhUveUdsh+DElv2N7hZnrF3yHPQSErrxxZt3e1qwDVH/duL+6gx6lbPVl8RiIdesl88Q3KiXIdLXge6Z/jy9ULRUVB3o+548phYsoSHfbTXgrznGHSAX2wIJxnuQjP2R7Xa5QAuW0BT4DegEEyzK8P7+ZYAWHCK1CQ6EFhwiWrBiIi0YjafV4Mred4IWbMLnzhkxhdp1v150JT2T/L8XzI1mHN/8jJ1cIMpu2rqTUtsMNLLZC8laMAvmu8LSVe+LsojyjdupuVeSdRXBNO5F8Uk9xC27FetZsshkt9WFFsxAIBo3vomxSy7fZEp2k8lasEkzBrftfLfon8muqgvHgnGyZL4gliImGj3h/JPDlW4Ez5hZxMdK9Tt2qFzItKEX5y+j48ePi+OJ6qKtQ8mOBfMnnX3tOCopfYezrswTFrLcHbsqxB/lRvD6b7fR3KKl4sMKm5I36CUuO2/hSvrn3ypxPAQavgsuGmRUJbJrCIRjwb6ONPn+Z8zTex8/saxwBDdhwX/+fcQsrSY+W7eREs7pceZgUzAcC45Pp+FjptL+A5Ui27xkHx/zy683GQPu3MJLz2+H90luPZDLbKadu/fR9/wtcAyX37FzL33DDVx19TFTLdERzubcYfkUl5QJafLrkOFYMPcf66VeRkmt+otM85IkRsiVnTcI9VL7ivURWBnkCC5bD3UsN5AYe64+Zgg+8k8VDcrN4+0dpOcNimPB4NzexldYBRgnlp0zGE24DMo5AWXF7MmFNOm+p4VYBORemTPemVzgSvDZBOpVXxrlP/ScqZZEIzcod4JzuUCJ4EAD49EKrpUl2uUa1YJLucBzwWgAMOPrPx0UrWAsIjGTpj8xz1RrNGhX5nggF3gqWGRCGk3i7hsWkPgSuUuDuk22b7RgCn7ltbeEXKNaMBs03N3JyoSDZ4JNuWPueFRcKGLB4jKKwyQl3pOViRaQBPytw6LBwSPv9SZzLTwRbModnfewqdaIcXcWGNVFOP3GSIBMbcKNHG6Fcb1eVmuuBZtyb817xNRqRMhre6MJFd80V4ItubZqARGTclXhWLAkc7H0dOjN9/H2tkanvZEb+GZDdt5giJsU2bE8wGl2OxJsyrU3aFVV1TQ2f6aYfsHIlluSMQYrO3cA4rgebcRlZMfyAtxKO5IctmA+CaZX8qbMMtUagYGRXXv2U+VPv4phQ7fgQRgxHhFKJnOGQe6Wbbulx/KCy9F1QyMoO38wwhbMNw+JKb1py/Y9plo1gQ8KAz+hCkaW/XH4L7O09zH4JnTfusjPHwxHVQRncOsOV9Fmzhgr0EF/oaiUZheWUCH/LJzngMJXafN3u8TxMGwZrmBkGgID7oW4Dtk5HNIla5izZ/ccCUY/MT6dWrYfRJtMIZhewSyAaOAEnZiOYdKC5hW7nzKaNaeEj9Xc79guQUPnpH/sSDAwJWMaxZKMWFH2EdfRmcanHe4FeTTpiYwLe9JTFY4FA0syZ7K9ulhZ9rEx8h+uZC1YgpDcVZrJDTDdE8qUj4UWHAB7dbHtlOQlK9dQXH3bsxS1oQUHwZSMhg9T7zU1x+n6YfnGg9my/WVowbUAydwZb99ziFgzIRZy6DrYQ8EAQtG41c8ITy7QghWjBStGC1ZMqIIxxW7vmYQi2L9MXRFTglGn4zWWmWJC1RIWTDDKYGwahNOj8YqYEoyV6Cxq+Zsf0LSCubx/B3N1UQDBkNsgg5LP60erP/yCRk14mLeH2bNxS8wIxjh0w+60jOVacecDz3KZNLGk9EzBLBJyWebaz9aL7Yhrhk42HiT3P7cqYkkw1i9MvOcp8b4VhuR2lNx6wEnBz+OBcV9rSm7ehz75vFxsQ2CNb1rX68Jf4+uGmKoiMP3vNw+ImDBllni4/FDlL+J1wewFFJ/YidZ+fipz123YSs1a8fGQvbqKCCAYoGFjybdwfWqPaQUv0e4fjH8JNr9kFa0oWyt+R6wr30opLbPrXi6IOcHAlDzaT3JNTY34if/vY8VXG76LnFwQrYKxyj2gYBBAsj2MzI1AtWAnugR3ptJVa4ScX38/HFwwsKqL8WdKRp0b0cy1iCrBLDOj3410NXelBuSMp/jmlxkSZftamJLtDd+68i2UEokGTUZUCYYM3G3FpxtyQl00aEqeMOVJ+vSLDZSCRSvRIBdElWA3QDKGSTHm4GTCVRVnjWAAyViGKnsvUpxVgqMRLVgxWrBitGDFaMGK0YIVowUrRgtWjBasGC1YMU2zjviEZY0isn78D43o8OjRWGtOAAAAAElFTkSuQmCC;",
        "leaf": base_style + "image=data:image/png,iVBORw0KGgoAAAANSUhEUgAAAFgAAABYCAYAAABxlTA0AAAAAXNSR0IArs4c6QAAAARnQU1BAACxjwv8YQUAAAAJcEhZcwAAFxEAABcRAcom8z8AAAikSURBVHhe7ZwJbBRVGMe3pUBrASkUlVMpV6EUQSlCCqhEjbYiIQEUETFyVEAr3hDwquCFVE2EYoTWCBTk8KgmiBfGqDEoRbkE5JByWW9UtJTC5/d/MwPD8na7OzOvu4vvS35pd3bezPS337735r039flSskijiKZZf2nBKtGCFaMFK0YLVowWrBgtWDFasGK0YMVowYrRghUTlYIbX8IX1lv+XqwRVYKb9SFfYiYlpPYlX1IP+T6xRtQIhlxfF2rf4wbasHE7jc57lF+nyfeVgYyPS+cyncWHJI4n26+uiQrBpty0jFzavfcAIU6cOEE33jY1NMnnXkoJLfrSkFH308hx0ykzeyT5knvK961rIi7YytxuOSz3oJBrxQlm+JiHapfcqCc1aXcFVR2tFuUK5y7hMh3l+9Y1ERV8WuaeLtcKSB5Rm2QW3Ljt5VT582+izKw5xbx/J/m+dU3EBFtyOXP3VBwSYhBHzSw8Wm38tCKoZC3YjwDVwosvv04LFr0tft+6fQ/d9eBs8TsCdXLA6kILtgG5cWa1UHFK7qLlq1lKGyoqXiVe7913iHz1utJtEx8TrxGoLqQNnxZsg7tQPfuNoH0HK4UMxOIV75GvQQZLuYhKSt8V2yr2/0gNL8jmbe1ofP5Msc2K2yc/Tr6G3U8dUwu2kdCVcoffLUQgFiNzIfeci1lKOhUveUdsh+DElv2N7hZnrF3yHPQSErrxxZt3e1qwDVH/duL+6gx6lbPVl8RiIdesl88Q3KiXIdLXge6Z/jy9ULRUVB3o+548phYsoSHfbTXgrznGHSAX2wIJxnuQjP2R7Xa5QAuW0BT4DegEEyzK8P7+ZYAWHCK1CQ6EFhwiWrBiIi0YjafV4Mred4IWbMLnzhkxhdp1v150JT2T/L8XzI1mHN/8jJ1cIMpu2rqTUtsMNLLZC8laMAvmu8LSVe+LsojyjdupuVeSdRXBNO5F8Uk9xC27FetZsshkt9WFFsxAIBo3vomxSy7fZEp2k8lasEkzBrftfLfon8muqgvHgnGyZL4gliImGj3h/JPDlW4Ez5hZxMdK9Tt2qFzItKEX5y+j48ePi+OJ6qKtQ8mOBfMnnX3tOCopfYezrswTFrLcHbsqxB/lRvD6b7fR3KKl4sMKm5I36CUuO2/hSvrn3ypxPAQavgsuGmRUJbJrCIRjwb6ONPn+Z8zTex8/saxwBDdhwX/+fcQsrSY+W7eREs7pceZgUzAcC45Pp+FjptL+A5Ui27xkHx/zy683GQPu3MJLz2+H90luPZDLbKadu/fR9/wtcAyX37FzL33DDVx19TFTLdERzubcYfkUl5QJafLrkOFYMPcf66VeRkmt+otM85IkRsiVnTcI9VL7ivURWBnkCC5bD3UsN5AYe64+Zgg+8k8VDcrN4+0dpOcNimPB4NzexldYBRgnlp0zGE24DMo5AWXF7MmFNOm+p4VYBORemTPemVzgSvDZBOpVXxrlP/ScqZZEIzcod4JzuUCJ4EAD49EKrpUl2uUa1YJLucBzwWgAMOPrPx0UrWAsIjGTpj8xz1RrNGhX5nggF3gqWGRCGk3i7hsWkPgSuUuDuk22b7RgCn7ltbeEXKNaMBs03N3JyoSDZ4JNuWPueFRcKGLB4jKKwyQl3pOViRaQBPytw6LBwSPv9SZzLTwRbModnfewqdaIcXcWGNVFOP3GSIBMbcKNHG6Fcb1eVmuuBZtyb817xNRqRMhre6MJFd80V4ItubZqARGTclXhWLAkc7H0dOjN9/H2tkanvZEb+GZDdt5giJsU2bE8wGl2OxJsyrU3aFVV1TQ2f6aYfsHIlluSMQYrO3cA4rgebcRlZMfyAtxKO5IctmA+CaZX8qbMMtUagYGRXXv2U+VPv4phQ7fgQRgxHhFKJnOGQe6Wbbulx/KCy9F1QyMoO38wwhbMNw+JKb1py/Y9plo1gQ8KAz+hCkaW/XH4L7O09zH4JnTfusjPHwxHVQRncOsOV9Fmzhgr0EF/oaiUZheWUCH/LJzngMJXafN3u8TxMGwZrmBkGgID7oW4Dtk5HNIla5izZ/ccCUY/MT6dWrYfRJtMIZhewSyAaOAEnZiOYdKC5hW7nzKaNaeEj9Xc79guQUPnpH/sSDAwJWMaxZKMWFH2EdfRmcanHe4FeTTpiYwLe9JTFY4FA0syZ7K9ulhZ9rEx8h+uZC1YgpDcVZrJDTDdE8qUj4UWHAB7dbHtlOQlK9dQXH3bsxS1oQUHwZSMhg9T7zU1x+n6YfnGg9my/WVowbUAydwZb99ziFgzIRZy6DrYQ8EAQtG41c8ITy7QghWjBStGC1ZMqIIxxW7vmYQi2L9MXRFTglGn4zWWmWJC1RIWTDDKYGwahNOj8YqYEoyV6Cxq+Zsf0LSCubx/B3N1UQDBkNsgg5LP60erP/yCRk14mLeH2bNxS8wIxjh0w+60jOVacecDz3KZNLGk9EzBLBJyWebaz9aL7Yhrhk42HiT3P7cqYkkw1i9MvOcp8b4VhuR2lNx6wEnBz+OBcV9rSm7ehz75vFxsQ2CNb1rX68Jf4+uGmKoiMP3vNw+ImDBllni4/FDlL+J1wewFFJ/YidZ+fipz123YSs1a8fGQvbqKCCAYoGFjybdwfWqPaQUv0e4fjH8JNr9kFa0oWyt+R6wr30opLbPrXi6IOcHAlDzaT3JNTY34if/vY8VXG76LnFwQrYKxyj2gYBBAsj2MzI1AtWAnugR3ptJVa4ScX38/HFwwsKqL8WdKRp0b0cy1iCrBLDOj3410NXelBuSMp/jmlxkSZftamJLtDd+68i2UEokGTUZUCYYM3G3FpxtyQl00aEqeMOVJ+vSLDZSCRSvRIBdElWA3QDKGSTHm4GTCVRVnjWAAyViGKnsvUpxVgqMRLVgxWrBitGDFaMGK0YIVowUrRgtWjBasGC1YMU2zjviEZY0isn78D43o8OjRWGtOAAAAAElFTkSuQmCC;",
        "dcgw": base_style + "image=data:image/png,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;",
        "server": base_style + "image=data:image/png,iVBORw0KGgoAAAANSUhEUgAAAFkAAABZCAMAAABi1XidAAAAAXNSR0IArs4c6QAAAARnQU1BAACxjwv8YQUAAAHCUExURQAQNgARNgARNQAAHAAAHQAAIQAAIwAAJAAAJQAAJgAAJwABJgABJwACKAADKQAEKgAFKwAGLAAHLAAHLQAILAAILQAILgAJLgAKLwALMAAMMAAMMQANMQANMgAOMgAOMwAPMwAPNAAQNAARNQASNQASNgILLwQOMgUWOQgTNwgYOwkVOQkZPAwcPgwcPw0dPw4eQA8aPA8cPg8fQRwrSx0sTB4pSR4tTCEwTyMyUSMzUiQzUiU0UyY1Uyk0Uis5Vy07WTA7WDA+XDRBXjU/XDdGYT1LZkBJZUBKZUNPaUdSbEdUbklSbEtXcExWb05ac1NedlVgeFljel5pgF9mfl9qgWBrgmZwhmxziHF6jnJ8kHN8kHR9kXV+knV/knZ/k3eAlHh/kniBlHiClHl/knuAk4CJmoaNnoePoImRoYuTo5GZqJSaqZacq5eerJeerZicq5ierZmdrJqfrpqhr6OntKmsua+1wLC0wLW6xL7BysLFztHU2tHU29TX3d/h5t/i5uLl6Obo6+fo7Ofp7Ojp7Orr7urs7+zt8PHy9PT19/X29/b29/b2+Pb3+Pf4+fj5+vn6+vv8/P3+/v7+/v////GBh4cAAAADdFJOU+jz9a/B8SsAAAAJcEhZcwAAFxEAABcRAcom8z8AAAImSURBVGhD7dj3UxNBFMDxRMDLYnJJFIgRiHBrLNiw994LKjYExV6x9441YgFr3v/rJfcu827XC7O5yy/Ofn/Km8x95mazk7m9CK9TUS2TtEzTMk3LtP9EtrIZ9bIWXl1JlhOpFatWKtebNPF6N1HONR98/mli/Jta4xOFZ3tYFxpOgtxtXoNauxD3rIggswGAn48vD59Ta/jKkz8A/dNQKeeVs8s/w9jOJiOmmtG09wu8XdCJTimvHD8MMNCIg1qNFwF201/RKxtDUNyQxkGuIyPtrUrJ7QAnGA6lBPmMLc/AQSyfmb8mMxsHqfQWgJNV5NNQ3Ognz1z96sftuX53nd5a/Z6rycYle2ut9/s2iGzuB3izrB0nsSAyb+s7v7Z1Dg5igWRuxtry+FEqmFwtLdO0TNMyTcs0LdO0TNMyTcs0LdMmk+1n/nU1ypM88w9CcVMKB7XMHQDH/OXEAYCzDf7HHP+6Gq4D7EriVMordyx8B18PMYMpFjPiR3/B6Dx6PvLKnB2xzyIv7t29r9adBy/t6/YlUCknyJyd+l06Q9fQ9+N0lWXZYtsejn4ofFSr8P71rc1eWJI5TzVbS5aqtribpYUjjCxznpulXLt8tv2XHE71l/MpfFMRvOnOgrtya//IjXAa6Wspi65sPMVtGbxHU8uiK8dvjoXVVed1kitbi3rDqsf5R3Nl3pkNq5wDVuTQ0zJNyzQt07RMq588JRKtT9HIXyTFPzou9sSWAAAAAElFTkSuQmCC;"
    }

    # Map 'graph-icon' values to the corresponding group used in 'custom_styles'
    icon_to_group_mapping = {
        "router": "dcgw",
        "switch": "leaf", # or "spine" depending on your specific use case
        "host": "server"
    }

    for node_name, node_info in nodes.items():
        # Check for 'graph-icon' label and map it to the corresponding group
        icon_label = node_info.get('labels', {}).get('graph-icon')
        if icon_label in icon_to_group_mapping:
            group = icon_to_group_mapping[icon_label]
        else:
            # Determine the group based on the node's name if 'graph-icon' is not specified
            if "client" in node_name:
                group = "server"
            elif "leaf" in node_name:
                group = "leaf"
            elif "spine" in node_name:
                group = "spine"
            elif "dcgw" in node_name:
                group = "dcgw"
            else:
                group = "default"  # Fallback to 'default' if none of the conditions are met

        style = custom_styles.get(group, base_style)
        x_pos, y_pos = positions[node_name]
        # Add each node to the diagram with the given x and y position.
        diagram.add_node(id=node_name, label=node_name, x_pos=x_pos, y_pos=y_pos, style=style, width=75, height=75)

    # Initialize a counter for links between the same nodes
    link_counter = defaultdict(lambda: 0)

    total_links_between_nodes = defaultdict(int)
    for link in links:
        source, target = link['source'], link['target']
        link_key = tuple(sorted([source, target]))
        total_links_between_nodes[link_key] += 1

    for link in links:
        source, target = link['source'], link['target']
        source_intf, target_intf = link['source_intf'], link['target_intf']
        source_tier = node_tiers.get(source.split(':')[0], -1)
        target_tier = node_tiers.get(target.split(':')[0], -1)
        link_key = tuple(sorted([source, target]))
        link_index = link_counter[link_key]

        # Increment link counter for next time
        link_counter[link_key] += 1
        total_links = total_links_between_nodes[link_key]

        source_tier = node_tiers[source]
        target_tier = node_tiers[target]

        unique_link_style = create_link_style(link_style, positions, source, target, source_tier, target_tier, link_index, total_links, orientation=args.orientation)

        # Add the link to the diagram with the determined unique style
        if not args.no_links:
            diagram.add_link(
                source=source, target=target,
                src_label=source_intf, trgt_label=target_intf,
                style=unique_link_style
            )

def main(filename, output_dir='./Output'):
    with open(filename, 'r') as file:
        containerlab_data = yaml.safe_load(file)

   # Nodes remain the same
    nodes = containerlab_data['topology']['nodes']

    # Prepare the links list by extracting source and target from each link's 'endpoints'
    links = []
    for link in containerlab_data['topology'].get('links', []):
        endpoints = link.get('endpoints')
        if endpoints:
            source_node, source_intf = endpoints[0].split(":")
            target_node, target_intf = endpoints[1].split(":")
            # Add link only if both source and target nodes exist
            if source_node in nodes and target_node in nodes:
                links.append({'source': source_node, 'target': target_node, 'source_intf': source_intf, 'target_intf': target_intf})

    if not args.include_unlinked_nodes:
        # Identifying linked nodes
        linked_nodes = set()
        for link in links:
            linked_nodes.add(link['source'])
            linked_nodes.add(link['target'])
        # Keep only linked nodes if --include-unlinked-nodes is not set
        nodes = {node: info for node, info in nodes.items() if node in linked_nodes}

    sorted_nodes, node_tiers, connections = assign_tiers(nodes, links)
    positions = calculate_positions(sorted_nodes, links, node_tiers, connections, orientation=args.orientation)

    # Create a draw.io diagram instance
    diagram = drawio_diagram()

    # Add a diagram page
    diagram.add_diagram("Network Topology")

    # Add nodes and links to the diagram
    add_nodes_and_links(diagram, nodes, positions, links, node_tiers)

    # Ensure the output directory exists
    output_folder = "./Output"
    os.makedirs(output_folder, exist_ok=True)

    # Correcting the output_filename construction to handle both .yaml and .yml extensions
    base_filename = os.path.basename(filename)
    if base_filename.endswith('.yaml'):
        new_filename = base_filename[:-5]  # Remove the last 5 characters (.yaml)
    elif base_filename.endswith('.yml'):
        new_filename = base_filename[:-4]  # Remove the last 4 characters (.yml)
    else:
        new_filename = base_filename  # No extension found, use as is
    output_filename = new_filename + ".drawio"

    
    # Save the diagram
    diagram.dump_file(filename=output_filename, folder=output_dir )

def parse_arguments():
    parser = argparse.ArgumentParser(description='Generate a topology diagram from a containerlab YAML file.')
    parser.add_argument('filename', help='The filename of the containerlab YAML file')
    parser.add_argument('--include-unlinked-nodes', action='store_true', help='Include nodes without any links in the topology diagram')
    parser.add_argument('--no-links', action='store_true', help='Do not draw links between nodes in the topology diagram')
    parser.add_argument('--output-dir', type=str, default='./Output', help='Specify the output directory for the topology diagram')
    parser.add_argument('--orientation', type=str, default='vertical', choices=['vertical', 'horizontal'], help='Specify the orientation of the topology diagram (vertical or horizontal)')
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_arguments()
    main(args.filename, args.output_dir)