from typing import Optional

from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor
from PyQt6.QtCore import Qt, QPointF
from models import *
from models.polygon import Polygon

class Canvas(QWidget):
    def __init__(self, parent=None):
        super().__init__()
        
       
        test_point = Point(350, 120)
        points = [[
                    Point(150, 100),
                    test_point,
                    Point(300, 300),
                    Point(120, 250),
                ],[
                    Point(300, 250),
                    test_point,
                    Point(100, 300),
                    Point(50, 300),
                ],[
                    Point(100, 100),
                    test_point,
                    Point(200, 300)
                ]            
        ]
        
        self.polygons = [Polygon(points[0]),
                         Polygon(points[1]),
                         Polygon(points[2])]
        

        self.dragged_point: Point | None = None
        self.dragged_polygon: Polygon | None = None
        self.last_mouse_pos: QPointF | None = None

        self.hovered_point: Optional[Point] = None
        self.hit_radius: float = 9.0

        self.setMouseTracking(True)

    def find_point_at(self, x: float, y: float) -> Optional[Point]:
        """Zwraca pierwszy punkt pod zadanymi współrzędnymi (od tyłu listy, by brać wierzchnie)."""
        for poly in reversed(self.polygons):
            for pt in reversed(poly.points):
                if pt.is_hit(x, y, self.hit_radius):
                    return pt
        return None
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position()

            target_pt = self.find_point_at(pos.x(), pos.y())
            if target_pt:
                self.dragged_point = target_pt
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                self.update()
                return

            for poly in reversed(self.polygons):
                if poly.contains(pos.x(), pos.y()):
                    self.dragged_polygon = poly  # <-- Zapamiętujemy TEN konkretny poly
                    self.last_mouse_pos = pos
                    self.setCursor(Qt.CursorShape.SizeAllCursor)
                    self.update()
                    return

    def mouseMoveEvent(self, event):
            pos = event.position()

            # A. Przeciąganie punktu
            if self.dragged_point is not None:
                self.dragged_point.move_to(pos.x(), pos.y())
                self.update()
                return

            # B. Przesuwanie całego wielokąta
            if self.dragged_polygon is not None and self.last_mouse_pos is not None:
                dx = pos.x() - self.last_mouse_pos.x()
                dy = pos.y() - self.last_mouse_pos.y()
                self.dragged_polygon.move_by(dx, dy)
                self.last_mouse_pos = pos
                self.update()
                return
            new_hovered = self.find_point_at(pos.x(), pos.y())
        
            # Jeśli stan najechania na punkt się zmienił, odświeżamy widok
            if new_hovered != self.hovered_point:
                self.hovered_point = new_hovered
                self.update()

            is_over_any_polygon = any(poly.contains(pos.x(), pos.y()) for poly in self.polygons)

            # Ustawienie odpowiedniego kształtu kursora
            if self.hovered_point is not None:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            elif is_over_any_polygon:
                self.setCursor(Qt.CursorShape.SizeAllCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)


    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragged_point = None
            self.dragged_polygon = None
            self.last_mouse_pos = None

            # Aktualizujemy kursor po puszczeniu przycisku
            pos = event.position()
            self.hovered_point = self.find_point_at(pos.x(), pos.y())
            is_over_any_polygon = any(poly.contains(pos.x(), pos.y()) for poly in self.polygons)

            if self.hovered_point:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            elif is_over_any_polygon:
                self.setCursor(Qt.CursorShape.SizeAllCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)

            self.update()

    # --- PĘTLA RYSOWANIA ---
    def paintEvent(self, event):
        painter = QPainter(self)
        # Wygładzanie krawędzi (antyaliasing)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Tło
        painter.fillRect(self.rect(), Qt.GlobalColor.white)

        for polygon in self.polygons:
            polygon.draw(painter)
            for pt in polygon.points:
                is_active = pt is self.dragged_point
                pt.draw(painter, radius=2.0, is_active=is_active)
        