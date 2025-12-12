# hover_tool.py
# Main plugin logic for Auto Hover Digitizer
# Contains: HoverVertexTool (map tool) and HoverVertexPlugin (plugin wrapper)

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor, QIcon
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
    """A map tool that highlights the nearest vertex when hovering."""

    TOLERANCE_PX = 8  # how close (in pixels) the cursor must be to a vertex

    def __init__(self, canvas, layer=None):
        super().__init__(canvas)
        self.canvas = canvas
        self.layer = layer
        self.index = None
        self.marker = None
        self._prepare_layer_and_index()

    def _prepare_layer_and_index(self):
        # Determine which layer to use (selected layer preferred)
        if not self.layer:
            selected = QgsProject.instance().layerTreeRoot().selectedLayersRecursive()
            if selected:
                self.layer = selected[0]
            else:
                # fallback: first vector layer in project
                for lyr in QgsProject.instance().mapLayers().values():
                    if lyr.type() == lyr.VectorLayer:
                        self.layer = lyr
                        break

        if not self.layer:
            print("HoverVertexTool: No vector layer found.")
            return

        # Build spatial index
        feats = list(self.layer.getFeatures())
        self.index = QgsSpatialIndex()
        for f in feats:
            self.index.insertFeature(f)

        print(f"HoverVertexTool: Using layer {self.layer.name()} with {len(feats)} features.")

    def canvasMoveEvent(self, event):
        if not self.layer or not self.index:
            return

        mupp = self.canvas.mapUnitsPerPixel()
        tolerance = self.TOLERANCE_PX * mupp

        # Convert mouse pixel to map coordinates
        p = self.canvas.getCoordinateTransform().toMapCoordinates(event.pos().x(), event.pos().y())
        cursor_pt = QgsPointXY(p.x(), p.y())

        # Build search rectangle
        rect = QgsGeometry.fromPointXY(cursor_pt).buffer(tolerance, 1).boundingBox()
        candidate_ids = self.index.intersects(rect)

        if not candidate_ids:
            self._clear_marker()
            return

        # Find nearest vertex in candidates
        nearest_vertex = None
        nearest_dist = None

        for fid in candidate_ids:
            feat = next(self.layer.getFeatures(QgsFeatureRequest(fid)))
            geom = feat.geometry()
            if geom is None or geom.isEmpty():
                continue

            # Extract vertices
            vertices = []
            gtype = geom.type()

            if gtype == QgsWkbTypes.PointGeometry:
                try:
                    vertices.append(QgsPointXY(geom.asPoint()))
                except:
                    pass
            else:
                try:
                    for poly in geom.asMultiPolygon():
                        for ring in poly:
                            vertices.extend([QgsPointXY(v.x(), v.y()) for v in ring])
                except:
                    try:
                        for pl in geom.asMultiPolyline():
                            for seg in pl:
                                vertices.extend([QgsPointXY(v.x(), v.y()) for v in seg])
                    except:
                        try:
                            for seg in geom.asPolyline():
                                vertices.extend([QgsPointXY(v.x(), v.y()) for v in seg])
                        except:
                            pass

            # Compute nearest
            for v in vertices:
                d = QgsGeometry.fromPointXY(v).distance(QgsGeometry.fromPointXY(cursor_pt))
                if nearest_dist is None or d < nearest_dist:
                    nearest_dist = d
                    nearest_vertex = v

        # Display marker if within tolerance
        if nearest_vertex and nearest_dist <= tolerance:
            self._show_marker(nearest_vertex)
        else:
            self._clear_marker()

    def _show_marker(self, pt):
        if not self.marker:
            self.marker = QgsVertexMarker(self.canvas)
            self.marker.setColor(QColor(255, 0, 0))
            self.marker.setIconSize(12)
            self.marker.setIconType(QgsVertexMarker.ICON_BOX)
            self.marker.setPenWidth(2)
        self.marker.setCenter(pt)

    def _clear_marker(self):
        if self.marker:
            self.canvas.scene().removeItem(self.marker)
            self.marker = None


# ===========================
#   PLUGIN WRAPPER
# ===========================

class HoverVertexPlugin:
    """Main plugin wrapper class loaded by QGIS."""

    def __init__(self, iface):
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.action = None
        self.tool = None

    def initGui(self):
        # Setup a toolbar button
        self.action = self.iface.addToolBarIcon(QIcon())
        self.action.setText("Hover Digitizer")
        self.action.triggered.connect(self.activate_tool)
        print("HoverVertexPlugin: GUI initialized.")

    def unload(self):
        if self.action:
            self.iface.removeToolBarIcon(self.action)
        if self.tool:
            self.canvas.unsetMapTool(self.tool)
        print("HoverVertexPlugin unloaded.")

    def activate_tool(self):
        # Create and set map tool
        self.tool = HoverVertexTool(self.canvas)
        self.canvas.setMapTool(self.tool)
        print("Hover digitizer tool activated.")
