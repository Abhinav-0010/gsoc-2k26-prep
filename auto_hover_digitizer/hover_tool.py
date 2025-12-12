# hover_tool.py
# Clean, final implementation for Auto Hover Digitizer plugin
# - HoverVertexTool: map tool that highlights nearest vertex on hover
# - HoverVertexPlugin: plugin wrapper creating QAction and toggling the tool

import os
from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon, QColor
from qgis.PyQt.QtCore import Qt
from qgis.gui import QgsMapTool, QgsVertexMarker
from qgis.core import (
    QgsSpatialIndex,
    QgsPointXY,
    QgsGeometry,
    QgsProject,
    QgsFeatureRequest,
    QgsWkbTypes
)

# ===========================
#   MAP TOOL (HOVER LOGIC)
# ===========================

class HoverVertexTool(QgsMapTool):
    """
    Map tool that highlights the nearest vertex when the cursor hovers close to it.
    This is a lightweight Python prototype intended for UX demonstration and plugins.
    """

    TOLERANCE_PX = 8  # pixel tolerance for hover detection (configurable)

    def __init__(self, canvas, layer=None):
        super().__init__(canvas)
        self.canvas = canvas
        self.layer = layer
        self.index = None
        self.marker = None
        self._prepare_layer_and_index()

    def _prepare_layer_and_index(self):
        """Choose a layer (selected layer preferred) and build a spatial index."""
        if not self.layer:
            # prefer selected layers (robust across API differences)
            try:
                selected = QgsProject.instance().layerTreeRoot().selectedLayersRecursive()
            except Exception:
                selected = []
            if selected:
                self.layer = selected[0]
            else:
                # fallback: first vector layer in project
                for lyr in QgsProject.instance().mapLayers().values():
                    if lyr.type() == lyr.VectorLayer:
                        self.layer = lyr
                        break

        if not self.layer:
            print("HoverVertexTool: No vector layer found. Select a vector layer and re-run.")
            return

        # Build spatial index (feature bounding boxes)
        feats = list(self.layer.getFeatures())
        self.index = QgsSpatialIndex()
        for f in feats:
            try:
                self.index.insertFeature(f)
            except Exception:
                pass

        print(f"HoverVertexTool: Using layer '{self.layer.name()}' with {len(feats)} features.")

    def canvasMoveEvent(self, event):
        """Handle mouse move events on the canvas and show nearest vertex marker if within tolerance."""
        if not self.layer or not self.index:
            return

        # map units per pixel -> convert pixel tolerance to map units
        mupp = self.canvas.mapUnitsPerPixel()
        tolerance_map = max(self.TOLERANCE_PX * mupp, 0.0)

        # map coordinate of cursor
        try:
            p = self.canvas.getCoordinateTransform().toMapCoordinates(event.pos().x(), event.pos().y())
        except Exception:
            # fallback for potential API differences
            p = self.canvas.getCoordinateTransform().toMapCoordinates(event.pos())
        cursor_pt = QgsPointXY(p.x(), p.y())

        # make small search bbox around cursor and query spatial index
        try:
            rect_geom = QgsGeometry.fromPointXY(cursor_pt).buffer(tolerance_map, 1).boundingBox()
            candidate_ids = self.index.intersects(rect_geom)
        except Exception:
            candidate_ids = []

        if not candidate_ids:
            self._clear_marker()
            return

        # iterate candidate features and find nearest vertex
        nearest_vertex = None
        nearest_dist = None

        for fid in candidate_ids:
            try:
                feat_iter = self.layer.getFeatures(QgsFeatureRequest(fid))
                feat = next(feat_iter)
            except Exception:
                continue

            geom = feat.geometry()
            if geom is None or geom.isEmpty():
                continue

            vertices = []
            gtype = geom.type()

            if gtype == QgsWkbTypes.PointGeometry:
                try:
                    vertices.append(QgsPointXY(geom.asPoint()))
                except Exception:
                    pass
            else:
                # try multi-polygon (rings), multi-polyline, polyline
                try:
                    for poly in geom.asMultiPolygon():
                        for ring in poly:
                            vertices.extend([QgsPointXY(v.x(), v.y()) for v in ring])
                except Exception:
                    try:
                        for pl in geom.asMultiPolyline():
                            for seg in pl:
                                vertices.extend([QgsPointXY(v.x(), v.y()) for v in seg])
                    except Exception:
                        try:
                            for seg in geom.asPolyline():
                                vertices.extend([QgsPointXY(v.x(), v.y()) for v in seg])
                        except Exception:
                            pass

            # compute nearest vertex from this feature
            for v in vertices:
                try:
                    d = QgsGeometry.fromPointXY(v).distance(QgsGeometry.fromPointXY(cursor_pt))
                except Exception:
                    continue
                if nearest_dist is None or d < nearest_dist:
                    nearest_dist = d
                    nearest_vertex = v

        # if nearest within tolerance_map -> show marker
        if nearest_vertex is not None and nearest_dist is not None and nearest_dist <= tolerance_map:
            self._show_marker(nearest_vertex)
        else:
            self._clear_marker()

    def _show_marker(self, pt):
        """Create or move the vertex marker to the given map coordinate."""
        if not self.marker:
            self.marker = QgsVertexMarker(self.canvas)
            self.marker.setColor(QColor(255, 0, 0))
            self.marker.setIconSize(12)
            self.marker.setIconType(QgsVertexMarker.ICON_BOX)
            self.marker.setPenWidth(2)
        try:
            self.marker.setCenter(pt)
        except Exception:
            # In rare cases setCenter can fail if pt invalid
            pass

    def _clear_marker(self):
        """Remove the marker if present."""
        if self.marker:
            try:
                self.canvas.scene().removeItem(self.marker)
            except Exception:
                pass
            self.marker = None


# ===========================
#   PLUGIN WRAPPER
# ===========================

class HoverVertexPlugin:
    """
    Plugin wrapper used by QGIS. QGIS calls classFactory() from __init__.py which must return an instance of this class.
    """

    def __init__(self, iface):
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.action = None
        self.tool = None

    def initGui(self):
        """Called when the plugin is enabled. Create a QAction and add it to the toolbar/menu."""
        # Try to load local icon.png if present
        icon = QIcon()
        try:
            base = os.path.dirname(__file__)
            icon_path = os.path.join(base, "icon.png")
            if os.path.exists(icon_path):
                icon = QIcon(icon_path)
        except Exception:
            icon = QIcon()

        # QAction with icon and label
        self.action = QAction(icon, "Hover Digitizer", self.iface.mainWindow())
        self.action.setCheckable(True)
        self.action.triggered.connect(self._toggle_tool)

        # add to toolbar and plugin menu (some API versions may have different method names)
        try:
            self.iface.addToolBarIcon(self.action)
        except Exception:
            # fallback: some QGIS builds may expose different API - ignore if fails
            pass

        try:
            self.iface.addPluginToMenu("&Auto Hover Digitizer", self.action)
        except Exception:
            pass

        print("HoverVertexPlugin: GUI initialized.")

    def unload(self):
        """Remove toolbar icon/menu and unset the tool when plugin is disabled/unloaded."""
        try:
            if self.action:
                # if tool active, unset it
                if hasattr(self, "tool") and self.canvas.mapTool() == self.tool:
                    self.canvas.unsetMapTool(self.tool)
                try:
                    self.iface.removeToolBarIcon(self.action)
                except Exception:
                    pass
                try:
                    self.iface.removePluginMenu("&Auto Hover Digitizer", self.action)
                except Exception:
                    pass
                self.action = None
        except Exception as e:
            print("HoverVertexPlugin unload error:", e)
        print("HoverVertexPlugin unloaded.")

    def _toggle_tool(self, checked):
        """Enable or disable the hover map tool based on QAction checked state."""
        if checked:
            # create tool instance (rebuild index on init) and set it as active map tool
            self.tool = HoverVertexTool(self.canvas)
            self.canvas.setMapTool(self.tool)
            print("Hover digitizer tool activated.")
        else:
            # deactivate
            if hasattr(self, "tool") and self.tool:
                try:
                    self.canvas.unsetMapTool(self.tool)
                except Exception:
                    pass
                self.tool = None
                print("Hover digitizer tool deactivated.")
