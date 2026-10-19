# Canvas connections

Edit `canvas_connections` in `gui_preferences.json`, then restart the GUI.
The existing rectangles, positions, actions, and loading states are preserved.
Connections are visual only; they do not run actions or impose dependencies.
Only edges with both rectangles visible in the same canvas are drawn.

## Settings

- `enabled`: enable/disable all connections.
- `color`: default Matplotlib color, such as `"#8A9BAE"`.
- `width`: default line width in points.
- `arrow`: show arrowheads (`true`) or plain lines (`false`).
- `show_ports`: show attachment dots on rectangle edges.
- `port_color`: dot color.
- `port_radius_px`: dot radius in display pixels.
- `port_offset_px`: distance the line leaves a rectangle before turning.
- `tabs`: connections grouped by main tab, then subtab. Each subtab contains a list of edges.
  For example, edit `canvas_connections.tabs.DMTS.File` for DMTS File connections.
  Go/noGo has `Folder or File`, `Animal`, and `Groups`; DMTS has `File`, `Animal`,
  and `Groups`; Lever has `File`. Empty lists mean no connections in that view.
- The styling settings above apply to all tabs. Individual edges can override line styling.
- Legacy flat `edges` lists are still supported. Group names organize the file;
  connections render only when both action IDs are visible in the same canvas.

Example edge (all fields except `from` and `to` are optional):

```json
{
  "from": "dmts_load",
  "to": "dmts_summary",
  "color": "#4C78A8",
  "width": 2,
  "arrow": true,
  "enabled": true,
  "from_port": "right",
  "to_port": "left"
}
```

Ports accept `left`, `right`, `top`, or `bottom`. Omit them for automatic selection.
For custom routing, add `"via": [[176, 70], [340, 70]]`: intermediate points
use the same top-left origin and display-pixel coordinates as the buttons.
Lines are drawn behind buttons. You can remove any edge without changing actions.

## Rectangle action IDs

| View | Available IDs |
|---|---|
| Go/noGo / File | `run_session`, `session_console`, `plot_ir_occupancy_by_sound`, `plot_performance`, `plot_hit_by_sound` |
| Go/noGo / Animal | `run_all_nwb`, `run_all_folders`, `plot_batch_session_performance`, `export_batch_data` |
| Go/noGo / Groups | `plot_group_averages` |
| DMTS / File | `dmts_load`, `dmts_summary`, `dmts_pretraining`, `dmts_matchonly`, `dmts_trial_examples`, `dmts_sound_performance`, `dmts_file_export`, `dmts_csv_load`, `dmts_csv_average` |
| DMTS / Animal | `dmts_batch`, `dmts_batch_plot`, `dmts_batch_save`, `dmts_batch_stim_hit`, `dmts_batch_outcome_counts` |
| DMTS / Groups | `dmts_groups_plot` |
| Lever / File | `lever_load`, `lever_plot`, `lever_crossing` |

Groups views currently have only one canvas rectangle, so there is no second
rectangle to connect. Native sidebar controls are not canvas nodes.

## Rectangle spacing

`canvas_layout` in `gui_preferences.json` controls spacing for Go/noGo, DMTS,
and Lever. Rectangles stay 150 x 50 display pixels.

```json
"canvas_layout": {
  "starting_margin_px": 15,
  "horizontal_gap_px": 25,
  "vertical_gap_px": 25
}
```

The starting margin is measured from the axes' top-left corner. Gaps are
edge-to-edge. Connectors follow the new positions automatically. Custom `via`
points remain absolute display-pixel coordinates and may need adjustment.
Restart the GUI after editing preferences.
