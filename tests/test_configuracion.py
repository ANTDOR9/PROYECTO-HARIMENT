"""Pruebas de GestorConfiguracion (hariment.gui.configuracion).

Solo se prueba la parte de lectura/escritura de JSON en disco: la
ventana grafica (VentanaConfiguracion) requiere un entorno con pantalla
y se valida manualmente / en la maquina del usuario.
"""

import json
import os

from hariment.gui.configuracion import GestorConfiguracion


def test_cargar_usa_configuracion_de_ejemplo_si_no_hay_una_del_usuario(tmp_path):
    ruta_ejemplo = tmp_path / "settings.example.json"
    ruta_usuario = tmp_path / "settings.json"

    ruta_ejemplo.write_text(json.dumps({"idioma_origen": "es", "idioma_destino": "en"}), encoding="utf-8")

    gestor = GestorConfiguracion(ruta_usuario=str(ruta_usuario), ruta_ejemplo=str(ruta_ejemplo))
    configuracion = gestor.cargar()

    assert configuracion["idioma_origen"] == "es"
    assert not ruta_usuario.exists()  # no se crea hasta que se guarda algo


def test_guardar_y_volver_a_cargar_conserva_los_cambios(tmp_path):
    ruta_ejemplo = tmp_path / "settings.example.json"
    ruta_usuario = tmp_path / "config" / "settings.json"  # carpeta que aun no existe

    ruta_ejemplo.write_text(json.dumps({"idioma_origen": "es", "idioma_destino": "en"}), encoding="utf-8")

    gestor = GestorConfiguracion(ruta_usuario=str(ruta_usuario), ruta_ejemplo=str(ruta_ejemplo))
    gestor.guardar({"idioma_origen": "es", "idioma_destino": "pt"})

    assert os.path.exists(ruta_usuario)
    configuracion_recargada = gestor.cargar()
    assert configuracion_recargada["idioma_destino"] == "pt"


def test_guardar_prioriza_configuracion_de_usuario_sobre_la_de_ejemplo(tmp_path):
    ruta_ejemplo = tmp_path / "settings.example.json"
    ruta_usuario = tmp_path / "settings.json"

    ruta_ejemplo.write_text(json.dumps({"idioma_destino": "en"}), encoding="utf-8")
    ruta_usuario.write_text(json.dumps({"idioma_destino": "pt"}), encoding="utf-8")

    gestor = GestorConfiguracion(ruta_usuario=str(ruta_usuario), ruta_ejemplo=str(ruta_ejemplo))
    configuracion = gestor.cargar()

    assert configuracion["idioma_destino"] == "pt"
