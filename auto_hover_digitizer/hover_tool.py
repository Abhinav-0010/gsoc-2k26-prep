

# hover_tool.py
# Clean implementation of vertex + segment hover detection plugin

import os
from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon, QColor
from qgis.gui import QgsMapTool, QgsVertexMarker, QgsRubberBand
from qgis.core import (
    QgsSpatialIndex,
    QgsPointXY,
    QgsGeometry,
    QgsProject,
    QgsFeatureRequest,
    QgsWkbTypes
)

# ===========================
#   MAP TOOL
# ===========================

class HoverVertexTool(QgsMapTool):
    TOLERANCE_PX = 8  # pixels

    def __init__(self, canvas, layer=None):
        super().__init__(canvas)
        self.canvas = canvas
        self.layer = layer
        self.index = None
        self.marker = None
        self.segment_band = None
        self._prepare_layer_and_index()

    def _prepare_layer_and_index(self):
        """Selects a vector layer and builds spatial index."""
        if not self.layer:
            try:
                selected = QgsProject.instance().layerTreeRoot().selectedLayersRecursive()
            except:
                selected = []

            if selected:
                self.layer = selected[0]
            else:
                for lyr in QgsProject.instance().mapLayers().values():
                    if lyr.type() == lyr.VectorLayer:
                        self.layer = lyr
                        break

        if not self.layer:
            print("No vector layer found.")
            return

        # Build spatial index (correct old-QGIS compatible method)
        feats = list(self.layer.getFeatures())
        self.index = QgsSpatialIndex()

        for f in feats:
            try:
                self.index.addFeature(f)
            except Exception:
                pass

        print(f"Using layer '{self.layer.name()}' with {len(feats)} features.")

    def canvasMoveEvent(self, event):
        """Runs on every mouse move — detect vertex + segment."""
        if not self.layer or not self.index:
            return

        mupp = self.canvas.mapUnitsPerPixel()
        tolerance = self.TOLERANCE_PX * mupp

        # cursor point in map coordinates
        p = self.canvas.getCoordinateTransform().toMapCoordinates(event.pos())
        cursor_pt = QgsPointXY(p.x(), p.y())

        # spatial index search
        rect = QgsGeometry.fromPointXY(cursor_pt).buffer(tolerance, 1).boundingBox()
        candidate_ids = self.index.intersects(rect)

        if not candidate_ids:
            self._clear_marker()
            self._clear_segment()
            return

        # --------------------------
        #  NEAREST VERTEX DETECTION
        # --------------------------

        nearest_vertex = None
        nearest_dist = None

        for fid in candidate_ids:
            feat = next(self.layer.getFeatures(QgsFeatureRequest(fid)))
            geom = feat.geometry()
            if geom.isEmpty():
                continue

            vertices = []

            try:
                for poly in geom.asMultiPolygon():
                    for ring in poly:
                        for v in ring:
                            vertices.append(QgsPointXY(v.x(), v.y()))
            except:
                try:
                    for seg in geom.asPolyline():
                        vertices.append(QgsPointXY(seg.x(), seg.y()))
                except:
                    pass

            for v in vertices:
                d = QgsGeometry.fromPointXY(v).distance(QgsGeometry.fromPointXY(cursor_pt))
                if nearest_dist is None or d < nearest_dist:
                    nearest_dist = d
                    nearest_vertex = v

        if nearest_vertex and nearest_dist <= tolerance:
            self._show_marker(nearest_vertex)
        else:
            self._clear_marker()

        # --------------------------
        #   SEGMENT DETECTION
        # --------------------------

        nearest_seg = None
        nearest_seg_dist = None

        for fid in candidate_ids:
            feat = next(self.layer.getFeatures(QgsFeatureRequest(fid)))
            geom = feat.geometry()
            if geom.isEmpty():
                continue

            segments = []

            # polygon rings
            try:
                for poly in geom.asMultiPolygon():
                    for ring in poly:
                        for i in range(len(ring) - 1):
                            p1 = QgsPointXY(ring[i].x(), ring[i].y())
                            p2 = QgsPointXY(ring[i+1].x(), ring[i+1].y())
                            segments.append((p1, p2))
            except:
                pass

            # polylines
            try:
                line = geom.asPolyline()
                for i in range(len(line) - 1):
                    p1 = QgsPointXY(line[i].x(), line[i].y())
                    p2 = QgsPointXY(line[i+1].x(), line[i+1].y())
                    segments.append((p1, p2))
            except:
                pass

            for (p1, p2) in segments:
                seg_geom = QgsGeometry.fromPolylineXY([p1, p2])
                d = seg_geom.distance(QgsGeometry.fromPointXY(cursor_pt))
                if nearest_seg_dist is None or d < nearest_seg_dist:
                    nearest_seg_dist = d
                    nearest_seg = (p1, p2)

        if nearest_seg and nearest_seg_dist <= tolerance:
            self._show_segment(nearest_seg[0], nearest_seg[1])
        else:
            self._clear_segment()

    # --------------------------
    #  MARKER + SEGMENT DRAWING
    # --------------------------

    def _show_marker(self, pt):
        if not self.marker:
            self.marker = QgsVertexMarker(self.canvas)
            self.marker.setColor(QColor(255, 0, 0))
            self.marker.setIconSize(12)
            self.marker.setIconType(QgsVertexMarker.ICON_BOX)

        self.marker.setCenter(pt)

    def _clear_marker(self):
        if self.marker:
            self.canvas.scene().removeItem(self.marker)
            self.marker = None

    def _show_segment(self, p1, p2):
        if not self.segment_band:
            self.segment_band = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
            self.segment_band.setColor(QColor(0, 0, 255))
            self.segment_band.setWidth(2)

        self.segment_band.reset(QgsWkbTypes.LineGeometry)
        self.segment_band.addPoint(p1, False)
        self.segment_band.addPoint(p2, True)
        self.segment_band.show()

    def _clear_segment(self):
        if self.segment_band:
            self.segment_band.reset(QgsWkbTypes.LineGeometry)
            self.segment_band.hide()


# ===========================
#   PLUGIN WRAPPER
# ===========================

class HoverVertexPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.action = None
        self.tool = None

    def initGui(self):
        icon = QIcon()
        self.action = QAction(icon, "Hover Digitizer", self.iface.mainWindow())
        self.action.setCheckable(True)
        self.action.triggered.connect(self._toggle_tool)

        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("&Auto Hover Digitizer", self.action)

    def unload(self):
        if self.action:
            self.iface.removeToolBarIcon(self.action)
            self.iface.removePluginMenu("&Auto Hover Digitizer", self.action)

    def _toggle_tool(self, checked):
        if checked:
            self.tool = HoverVertexTool(self.canvas)
            self.canvas.setMapTool(self.tool)
        else:
            self.canvas.unsetMapTool(self.tool)
            self.tool = None
