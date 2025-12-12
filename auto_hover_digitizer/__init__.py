# __init__.py for the auto_hover_digitizer plugin

from .hover_tool import HoverVertexPlugin

def classFactory(iface):
    """
    QGIS calls this function to load the plugin.
    'iface' is the QGIS interface instance.
    """
    return HoverVertexPlugin(iface)
