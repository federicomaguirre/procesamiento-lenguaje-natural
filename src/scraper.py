#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Web Scraper para Lectulandia (Categoría: Clásico)
Desarrollado para la Unidad 1 - Extracción y procesamiento de texto
Curso de Procesamiento del Lenguaje Natural

Este script automatiza la extracción de metadatos y sinopsis de libros de la categoría "Clásico"
utilizando Playwright para la navegación respetuosa y BeautifulSoup para el análisis del HTML.
La selección de libros se realiza bajo un criterio de selección aleatoria (Muestreo Aleatorio Simple).
"""

import os
import re
import sys
import time
import random
import argparse
import logging
from datetime import datetime
import urllib.request
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
import pandas as pd
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# Configuración del registro de log (Logging)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("extraction.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)

# Configuración del agente de usuario (User-Agent) para emular navegación humana
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def parse_arguments():
    """Parsea los argumentos de línea de comandos."""
    parser = argparse.ArgumentParser(
        description="Scraper automatizado de libros de la categoría Clásicos de Lectulandia."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Cantidad exacta de libros a extraer. Por defecto es 100."
    )
    parser.add_argument(
        "--output",
        type=str,
        default=os.path.join("data", "libros.csv"),
        help="Ruta del archivo CSV de salida. Por defecto es 'data/libros.csv'."
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Semilla para la selección aleatoria reproducible. Por defecto es 42."
    )
    parser.add_argument(
        "--headless",
        type=bool,
        default=True,
        help="Ejecutar en modo segundo plano (sin interfaz visual). Por defecto es True."
    )
    return parser.parse_args()


def cargar_robots_txt(base_url):
    """
    Descarga y parsea robots.txt del sitio para respetar sus reglas de acceso.
    Se usa urllib con nuestro User-Agent (en vez de RobotFileParser.read(), que
    usa el User-Agent por defecto de Python y es bloqueado con 403 por Cloudflare,
    lo que haría que RobotFileParser interprete el sitio entero como prohibido).
    """
    parsed = urlparse(base_url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = RobotFileParser()
    rp.set_url(robots_url)
    try:
        request = urllib.request.Request(robots_url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=10) as response:
            contenido = response.read().decode("utf-8", errors="replace")
        rp.parse(contenido.splitlines())
        logger.info(f"robots.txt cargado correctamente desde: {robots_url}")
    except Exception as e:
        logger.warning(f"No se pudo leer robots.txt ({e}). Se continuará sin restricciones adicionales.")
        return None
    return rp


def permitido_por_robots(robots_parser, url):
    """Verifica si una URL puede visitarse según robots.txt. Si no hay parser disponible, permite por defecto."""
    if robots_parser is None:
        return True
    return robots_parser.can_fetch(USER_AGENT, url)


def init_playwright(p, headless=True):
    """Inicia el navegador Chromium con políticas seguras y User-Agent."""
    logger.info("Iniciando navegador Chromium...")
    browser = p.chromium.launch(headless=headless)
    context = browser.new_context(
        user_agent=USER_AGENT,
        viewport={"width": 1280, "height": 800}
    )
    # Establecer tiempos de espera prudentes
    context.set_default_timeout(30000)
    return browser, context


def extract_book_urls(context, base_url, robots_parser=None):
    """
    Recorre la categoría seleccionada en Lectulandia para obtener todas las URLs de libros disponibles.
    Esto permite conformar el universo total de libros para el muestreo aleatorio.
    """
    logger.info(f"Fase 1: Recopilando URLs de libros desde la categoría: {base_url}")
    page = context.new_page()
    book_urls = set()
    current_page_idx = 1

    # Lectulandia tiene un sistema de paginación /page/N/
    while True:
        target_url = base_url if current_page_idx == 1 else f"{base_url}page/{current_page_idx}/"

        if not permitido_por_robots(robots_parser, target_url):
            logger.warning(f"robots.txt prohíbe acceder a {target_url}. Deteniendo recolección del catálogo.")
            break

        logger.info(f"Navegando a página del catálogo: {target_url}")

        try:
            response = page.goto(target_url, wait_until="domcontentloaded")
            # Si el código de estado es 404, significa que hemos pasado la última página
            if response and response.status == 404:
                logger.info(f"Fin del catálogo detectado en la página {current_page_idx} (Error 404 esperado).")
                break
                
            # Pequeña pausa para simular lectura humana y asegurar la carga del DOM
            time.sleep(random.uniform(1.0, 2.0))
            
            html_content = page.content()
            soup = BeautifulSoup(html_content, "html.parser")
            
            # Buscar todos los enlaces de libros en el catálogo
            page_links = 0
            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"]
                # Normalizar a URL absoluta
                full_url = urljoin(target_url, href)
                
                # Un enlace a un libro de Lectulandia típicamente contiene '/book/<slug>/' y no es de paginación ni login
                if "/book/" in full_url and "/page/" not in full_url and "lectulandia.co" in full_url:
                    # Normalizar eliminando parámetros o hashes si los hubiera
                    clean_url = full_url.split("#")[0].split("?")[0]
                    # Asegurar que termina en barra
                    if not clean_url.endswith("/"):
                        clean_url += "/"

                    # Descartar el listado general (".../book/") que no es una ficha de libro individual
                    if clean_url.rstrip("/").endswith("/book"):
                        continue

                    if not permitido_por_robots(robots_parser, clean_url):
                        continue

                    if clean_url not in book_urls:
                        book_urls.add(clean_url)
                        page_links += 1
            
            logger.info(f"Encontrados {page_links} libros nuevos en la página {current_page_idx}. Total acumulado: {len(book_urls)}")
            
            # Si no se encontraron enlaces nuevos, es muy probable que hayamos llegado al fin del listado
            if page_links == 0:
                logger.info("No se encontraron enlaces de libros en esta página. Finalizando recolección de catálogo.")
                break
                
            # Control de seguridad para evitar loops infinitos en entornos de prueba
            if current_page_idx >= 35: # Lectulandia tiene un límite de páginas por género
                logger.info("Alcanzado el límite máximo de páginas de seguridad.")
                break
                
            current_page_idx += 1
            
        except Exception as e:
            logger.error(f"Error al analizar la página del catálogo {current_page_idx}: {e}")
            break
            
    page.close()
    return list(book_urls)


def scrape_book_details(context, url, category_origin, robots_parser=None):
    """
    Visita la ficha individual de un libro y extrae sus metadatos y sinopsis.
    """
    if not permitido_por_robots(robots_parser, url):
        logger.warning(f"robots.txt prohíbe acceder a {url}. Omitiendo libro.")
        return None

    logger.info(f"Extrayendo metadatos del libro: {url}")
    page = context.new_page()

    try:
        page.goto(url, wait_until="domcontentloaded")
        # Simular lectura humana con pausas de cortesía variables
        time.sleep(random.uniform(1.5, 3.5))
        
        html_content = page.content()
        soup = BeautifulSoup(html_content, "html.parser")

        # El contenedor principal de la ficha del libro (evita capturar el header
        # del sitio y los widgets de la barra lateral, que también matchean estos selectores)
        book_container = soup.find(id="book") or soup

        # 1. Título (Búsqueda en el h1 dentro del bloque #title de la ficha)
        title_tag = book_container.select_one("#title h1") or soup.select_one(".book-title")
        title = title_tag.get_text(strip=True) if title_tag else "Sin título"

        # En Lectulandia, los libros a veces tienen el título con el autor: "Título · Autor"
        # Limpiamos el título si contiene el separador "·" o " - "
        if " · " in title:
            title = title.split(" · ")[0].strip()

        # 2. Autores (Enlaces que contienen /autor/, acotado a la ficha del libro)
        author_tags = book_container.select('a[href*="/autor/"]')
        authors_list = [a.get_text(strip=True) for a in author_tags if a.get_text(strip=True)]
        authors = ", ".join(authors_list) if authors_list else "Autor no especificado"

        # 3. Géneros (Enlaces que contienen /genero/, acotado a la ficha del libro)
        genre_tags = book_container.select('a[href*="/genero/"]')
        genres_list = [g.get_text(strip=True) for g in genre_tags if g.get_text(strip=True)]
        # Excluimos de los géneros el valor de búsqueda principal si es necesario o los guardamos todos
        genres = ", ".join(genres_list) if genres_list else "Sin género"

        # 4. Serie o saga (Enlaces que contienen /serie/, acotado a la ficha del libro)
        serie_tag = book_container.select_one('a[href*="/serie/"]')
        serie = "No aplica"
        if serie_tag:
            serie_text = serie_tag.get_text(strip=True)
            # A veces el texto de la serie tiene un número al final (ej. "Serie - 1")
            # Lo extraemos tal cual aparece
            serie = serie_text if serie_text else "No aplica"
            
        # 5. Sinopsis (Búsqueda en div con id="sinopsis" o clase "sinopsis" o "descripcion")
        sinopsis_div = soup.find(id="sinopsis") or soup.find(class_="sinopsis") or soup.find(class_="descripcion")
        if sinopsis_div:
            # Unir el texto de todos los párrafos de la sinopsis para unificar formato
            paragraphs = sinopsis_div.find_all("p")
            if paragraphs:
                sinopsis = " ".join([p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)])
            else:
                sinopsis = sinopsis_div.get_text(strip=True)
        else:
            sinopsis = "Sin sinopsis"
            
        # Limpieza de espacios en blanco duplicados o saltos de línea molestos
        sinopsis = re.sub(r'\s+', ' ', sinopsis).strip()
        
        # 6. Portada (Opcional - Imagen principal en el bloque #cover de la ficha)
        cover_tag = book_container.select_one("#cover img") or soup.select_one(".book-cover img")
        url_portada = urljoin(url, cover_tag["src"]) if cover_tag and cover_tag.get("src") else "No disponible"
        
        # Estructurar registro de salida
        book_data = {
            "titulo": title,
            "autores": authors,
            "generos": genres,
            "serie": serie,
            "sinopsis": sinopsis,
            "url_libro": url,
            "categoria_origen": category_origin,
            "fecha_extraccion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "url_portada": url_portada
        }
        
        logger.info(f"Éxito: Se extrajo '{title}' por {authors}")
        page.close()
        return book_data
        
    except Exception as e:
        logger.error(f"Fallo al extraer el libro {url}: {e}")
        page.close()
        return None


def main():
    args = parse_arguments()
    
    # Crear carpeta data de salida si no existe
    os.makedirs(os.path.dirname(args.output), exist_ok=True)

    # Eliminar salida previa para evitar acumular registros de corridas anteriores
    if os.path.exists(args.output):
        logger.info(f"Eliminando archivo de salida previo '{args.output}' para iniciar una corrida limpia.")
        os.remove(args.output)

    # Configurar semilla de aleatoriedad para reproducibilidad
    random.seed(args.seed)
    
    base_category_url = "https://ww3.lectulandia.co/genero/clasico/"
    category_name = "Clásico"

    # Cargar robots.txt para respetar las restricciones de acceso del sitio
    robots_parser = cargar_robots_txt(base_category_url)
    if not permitido_por_robots(robots_parser, base_category_url):
        logger.error(f"robots.txt prohíbe acceder a {base_category_url}. Abortando proceso.")
        return

    # Registramos inicio
    logger.info("=== INICIANDO PROCESO DE EXTRACCIÓN ===")
    logger.info(f"Configuración: Límite de libros={args.limit}, Semilla aleatoria={args.seed}")
    
    start_time = time.time()
    
    with sync_playwright() as p:
        browser, context = init_playwright(p, headless=args.headless)
        
        try:
            # 1. Obtener todas las URLs del catálogo para nuestro Muestreo Aleatorio Simple
            all_urls = extract_book_urls(context, base_category_url, robots_parser=robots_parser)
            total_available = len(all_urls)
            
            if total_available == 0:
                logger.error("No se pudieron recopilar URLs del catálogo. Abortando proceso.")
                browser.close()
                return
                
            logger.info(f"Universo total recopilado: {total_available} libros disponibles.")
            
            # Ajustamos el límite si el catálogo tiene menos libros de los pedidos (muy improbable en Clásicos)
            target_limit = min(args.limit, total_available)
            
            # 2. Selección Aleatoria de las URLs que procesaremos
            logger.info(f"Seleccionando aleatoriamente {target_limit} libros únicos (Semilla {args.seed})...")
            selected_urls = random.sample(all_urls, target_limit)
            
            extracted_books = []
            
            # 3. Visitar y extraer datos de cada una de las fichas individuales
            for i, url in enumerate(selected_urls, 1):
                logger.info(f"Progreso: [{i}/{target_limit}]")
                book_data = scrape_book_details(context, url, category_name, robots_parser=robots_parser)
                
                if book_data:
                    extracted_books.append(book_data)
                    
                    # Guardado Incremental para evitar pérdidas por fallos a mitad de proceso
                    # Creamos un DataFrame intermedio y lo volcamos al CSV
                    df_incremental = pd.DataFrame([book_data])
                    
                    # Si es el primer elemento, creamos el archivo con encabezados, si no, añadimos sin encabezados
                    if not os.path.exists(args.output):
                        df_incremental.to_csv(args.output, index=False, encoding="utf-8-sig")
                    else:
                        df_incremental.to_csv(args.output, mode='a', header=False, index=False, encoding="utf-8-sig")
                        
                # Pausa adicional entre lotes pequeños de scraping para un comportamiento óptimo
                if i % 10 == 0:
                    cooldown = random.uniform(5.0, 10.0)
                    logger.info(f"Lote de 10 completado. Pausa de cortesía prolongada (Enfriamiento) de {cooldown:.2f} segundos...")
                    time.sleep(cooldown)
            
            # 4. Fase de Control de Calidad y Deduplicación de Datos Finales con pandas
            if os.path.exists(args.output):
                logger.info("Fase de Control de Calidad: Validando e integrando dataset...")
                df_final = pd.read_csv(args.output, encoding="utf-8-sig")
                
                # Quitar duplicados por URL de ficha para garantizar la integridad
                initial_count = len(df_final)
                df_final.drop_duplicates(subset=["url_libro"], keep="first", inplace=True)
                final_count = len(df_final)
                
                if initial_count != final_count:
                    logger.info(f"Control de Duplicados: Se eliminaron {initial_count - final_count} registros duplicados de manera segura.")
                
                # Validación de títulos obligatorios
                empty_titles = df_final["titulo"].isna().sum()
                if empty_titles > 0:
                    logger.warning(f"Control de Títulos: Se encontraron {empty_titles} registros sin título. Limpiándolos...")
                    df_final.dropna(subset=["titulo"], inplace=True)
                
                # Guardamos el archivo final consolidado y limpio
                df_final.to_csv(args.output, index=False, encoding="utf-8-sig")
                logger.info(f"Dataset consolidado finalizado con éxito en '{args.output}'. Cantidad de registros válidos: {len(df_final)}")
            else:
                logger.error("No se pudo generar ningún registro válido durante el scraping.")
                
        finally:
            logger.info("Cerrando navegador...")
            browser.close()
            
    end_time = time.time()
    elapsed = end_time - start_time
    logger.info(f"=== PROCESO COMPLETADO EN {elapsed:.2f} SEGUNDOS ({elapsed/60:.2f} MINUTOS) ===")


if __name__ == "__main__":
    main()
