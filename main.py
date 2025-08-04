import requests
import re
import json


def replace_label_in_expr(expr, old_label, old_value, new_label, new_value):
    """
    Replaces PromQL label matchers in expressions, including:
    - =   (exact match)
    - !=  (negation)
    - =~  (regex match)
    - !~  (regex negation)

    Handles both single and double quotes.
    """

    def replacer(match):
        key = match.group("key")
        op = match.group("op")
        quote = match.group("quote")
        val = match.group("val")
        if key == old_label and val == old_value:
            return f'{new_label}{op}{quote}{new_value}{quote}'
        return match.group(0)

    pattern = re.compile(
        r'(?P<key>[a-zA-Z_][a-zA-Z0-9_]*)\s*(?P<op>=~|!~|=|!=)\s*(?P<quote>["\'])(?P<val>[^"\']*?)(?P=quote)'
    )
    return pattern.sub(replacer, expr)


def get_all_folders(grafana_url, headers):
    url = f"{grafana_url}/api/folders"
    res = requests.get(url, headers=headers)
    res.raise_for_status()
    return res.json()


def get_folder_id_by_name(folder_name, grafana_url, headers):
    folders = get_all_folders(grafana_url, headers)
    for folder in folders:
        if folder['title'] == folder_name:
            return folder['id']
    return None


def get_dashboards_in_folder(folder_id, grafana_url, headers):
    url = f"{grafana_url}/api/search?type=dash-db&folderIds={folder_id}"
    res = requests.get(url, headers=headers)
    res.raise_for_status()
    return res.json()


def get_dashboard(uid, grafana_url, headers):
    url = f"{grafana_url}/api/dashboards/uid/{uid}"
    res = requests.get(url, headers=headers)
    res.raise_for_status()
    return res.json()


def update_dashboard(dashboard_data, grafana_url, headers):
    url = f"{grafana_url}/api/dashboards/db"
    res = requests.post(url, headers=headers, data=json.dumps(dashboard_data))
    res.raise_for_status()
    return res.json()


def extract_panels(panels):
    all_panels = []
    for panel in panels:
        if 'panels' in panel:
            all_panels.extend(extract_panels(panel['panels']))
        else:
            all_panels.append(panel)
    return all_panels


def process_dashboard(dashboard_obj, old_label, old_value, new_label, new_value, folder_title, log_entries, grafana_url,
                      headers):
    dashboard = dashboard_obj['dashboard']
    title = dashboard.get('title', 'Unnamed Dashboard')
    panels = dashboard.get('panels', [])
    all_panels = extract_panels(panels)
    modified = False

    for panel in all_panels:
        targets = panel.get("targets", [])
        for target in targets:
            expr = target.get("expr")
            if expr and old_label in expr and old_value in expr:
                new_expr = replace_label_in_expr(expr, old_label, old_value, new_label, new_value)
                if new_expr != expr:
                    log_entries.append(
                        f"{folder_title}: {title}: {panel.get('title', 'Unnamed Panel')}\n"
                        f"  BEFORE: {expr}\n"
                        f"  AFTER:  {new_expr}"
                    )
                    target["expr"] = new_expr
                    modified = True

    if modified:
        dashboard_obj['dashboard']['id'] = dashboard.get('id')
        dashboard_obj['overwrite'] = True
        dashboard_obj['folderId'] = dashboard_obj.get('meta', {}).get('folderId', 0)  # Preserve folder
        update_dashboard(dashboard_obj, grafana_url, headers)


def run(grafana_url, api_key, folder_name, old_label, old_value, new_label, new_value, log_file="changes_log.txt"):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    folder_id = get_folder_id_by_name(folder_name, grafana_url, headers)
    if folder_id is None:
        print(f"Folder '{folder_name}' not found.")
        return

    dashboards = get_dashboards_in_folder(folder_id, grafana_url, headers)
    log_entries = []

    for dash in dashboards:
        uid = dash.get('uid')
        if not uid:
            continue
        dash_data = get_dashboard(uid, grafana_url, headers)
        process_dashboard(dash_data, old_label, old_value, new_label, new_value, folder_name, log_entries, grafana_url,
                          headers)

    # Save log
    with open(log_file, 'w') as f:
        for entry in log_entries:
            f.write(entry + '\n')

    print(f"Done. {len(log_entries)} changes written to {log_file}")


run(
    grafana_url="http://localhost:3000",
    folder_name="test-label-replace",
    old_label="bla",
    old_value="bli",
    new_label="roni",
    new_value="taktook"
)
