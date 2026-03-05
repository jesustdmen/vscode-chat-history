"""
pipeline/viewer/i18n.py — Internacionalização do Chat Viewer

Suporta: pt-BR (padrão), en-US, es-ES.
Uso: from pipeline.viewer.i18n import get_translation, LANGUAGE_OPTIONS, TRANSLATIONS
"""

from __future__ import annotations

TRANSLATIONS: dict[str, dict] = {
    # -------------------------------------------------------------------------
    # Português (Brasil) — padrão
    # -------------------------------------------------------------------------
    "pt-BR": {
        # Sidebar
        "app_title":            "💬 Chat Viewer",
        "sessions_loaded":      "**{n}** sessões carregadas",
        "theme_to_light":       "☀️ Tema claro",
        "theme_to_dark":        "🌙 Tema escuro",
        "search_placeholder":   "🔍 Buscar por título ou palavra-chave",
        "source_filter_label":  "Fonte",
        "hide_empty":           "Ocultar sessões vazias",
        "sessions_found":       "{n} sessão(ões) encontrada(s)",
        "no_sessions_found":    "🔍 Nenhuma sessão encontrada.<br>Tente outros termos de busca.",
        "session_select_label": "Sessão:",
        "run_pipeline_btn":     "🔄 Executar pipeline",
        "pipeline_starting":    "Iniciando pipeline...",
        "pipeline_success":     "Pipeline concluído! Recarregando dados...",
        "pipeline_error":       "Pipeline encerrou com erro. Veja o log acima.",
        "pipeline_launch_error":"Erro ao iniciar pipeline: {exc}",
        "language_label":       "🌐 Idioma",

        # Tabs
        "tab_conversation":     "💬 Conversa",
        "tab_diary":            "📅 Diário de Atividades",
        "tab_workspaces":       "🗂️ Workspaces",

        # Mensagens de chat
        "role_user":            "Você",
        "role_assistant":       "Assistente",
        "copy_text":            "📋 Copiar texto",
        "tool_args":            "Argumentos:",

        # Tab Conversa — stat bar
        "stat_questions":       "Perguntas",
        "stat_answers":         "Respostas",
        "stat_toolcalls":       "Tool calls",
        "stat_date":            "Data",
        "stat_sync":            "Últ. sinc.",

        # Tab Conversa — exportação
        "save_to_workspace":    "📂 Salvar no workspace",
        "workspace_not_id":     "Workspace não identificado para esta sessão.",
        "save_file_btn":        "⬇️ Salvar arquivo",
        "saved_success":        "✅ Salvo em: `{dest}`",
        "save_error":           "Erro ao salvar: {exc}",
        "export_json_btn":      "⬇️ Exportar JSON",
        "no_messages":          "Nenhuma mensagem encontrada para esta sessão.",
        "show_tool_calls":      "Mostrar tool calls",

        # Tab Diário
        "diary_title":          "Diário de Atividades",
        "diary_caption":        "Sessões agrupadas por dia — ideal para documentar o que foi feito.",
        "diary_search":         "🔍 Buscar por título ou thread ID",
        "date_from":            "De:",
        "date_to":              "Até:",
        "no_diary_sessions":    "Nenhuma sessão encontrada para os filtros aplicados.<br>Tente ampliar o intervalo de datas ou limpar a busca.",
        "diary_count":          "{total} sessão(ões) em {days} dia(s)",
        "day_header_meta":      "{n} sessão/sessões · {u}U {a}A",
        "diary_meta":           "{u} perguntas · {a} respostas",
        "goto_conversation":    "Abrir no Conversa",

        # Tab Workspaces
        "workspaces_title":     "Workspaces",
        "no_workspaces":        "Nenhum workspace encontrado.<br>Execute o pipeline para atualizar os dados.",
        "workspaces_count":     "{n} workspace(s) com sessões de chat registradas.",
        "filter_by_folder":     "🔍 Filtrar por pasta",
        "no_ws_filter":         "Nenhum workspace encontrado para o filtro aplicado.",
        "ws_first":             "Primeira sessão",
        "ws_last":              "Última",
        "ws_sessions":          "{n} sessão(ões)",
        "ws_questions":         "{u} perguntas",
        "ws_answers":           "{a} respostas",
        "expand_sessions":      "Ver {n} sessão(ões) de '{folder}'",

        # Estados gerais
        "no_data_error":        "Arquivo `sessions.jsonl` não encontrado em:\n`{path}`\n\nExecute o pipeline primeiro:\n```\npython pipeline/02_normalize/normalize.py\n```",
        "no_sessions_main":     "Nenhuma sessão disponível.<br>Execute o pipeline para carregar os dados.",
        "select_session":       "Selecione uma sessão na barra lateral.",
        "no_title":             "Sem título",
        "loading_data":         "Carregando dados...",

        # Dias da semana
        "weekdays": {
            "Monday":    "Segunda-feira",
            "Tuesday":   "Terça-feira",
            "Wednesday": "Quarta-feira",
            "Thursday":  "Quinta-feira",
            "Friday":    "Sexta-feira",
            "Saturday":  "Sábado",
            "Sunday":    "Domingo",
        },
    },

    # -------------------------------------------------------------------------
    # English (US)
    # -------------------------------------------------------------------------
    "en-US": {
        # Sidebar
        "app_title":            "💬 Chat Viewer",
        "sessions_loaded":      "**{n}** sessions loaded",
        "theme_to_light":       "☀️ Light theme",
        "theme_to_dark":        "🌙 Dark theme",
        "search_placeholder":   "🔍 Search by title or keyword",
        "source_filter_label":  "Source",
        "hide_empty":           "Hide empty sessions",
        "sessions_found":       "{n} session(s) found",
        "no_sessions_found":    "🔍 No sessions found.<br>Try different search terms.",
        "session_select_label": "Session:",
        "run_pipeline_btn":     "🔄 Run pipeline",
        "pipeline_starting":    "Starting pipeline...",
        "pipeline_success":     "Pipeline complete! Reloading data...",
        "pipeline_error":       "Pipeline exited with error. See log above.",
        "pipeline_launch_error":"Error starting pipeline: {exc}",
        "language_label":       "🌐 Language",

        # Tabs
        "tab_conversation":     "💬 Conversation",
        "tab_diary":            "📅 Activity Log",
        "tab_workspaces":       "🗂️ Workspaces",

        # Chat messages
        "role_user":            "You",
        "role_assistant":       "Assistant",
        "copy_text":            "📋 Copy text",
        "tool_args":            "Arguments:",

        # Stat bar
        "stat_questions":       "Questions",
        "stat_answers":         "Answers",
        "stat_toolcalls":       "Tool calls",
        "stat_date":            "Date",
        "stat_sync":            "Last sync",

        # Export
        "save_to_workspace":    "📂 Save to workspace",
        "workspace_not_id":     "Workspace not identified for this session.",
        "save_file_btn":        "⬇️ Save file",
        "saved_success":        "✅ Saved to: `{dest}`",
        "save_error":           "Error saving: {exc}",
        "export_json_btn":      "⬇️ Export JSON",
        "no_messages":          "No messages found for this session.",
        "show_tool_calls":      "Show tool calls",

        # Activity Log tab
        "diary_title":          "Activity Log",
        "diary_caption":        "Sessions grouped by day — great for reviewing what you worked on.",
        "diary_search":         "🔍 Search by title or thread ID",
        "date_from":            "From:",
        "date_to":              "To:",
        "no_diary_sessions":    "No sessions found for the applied filters.<br>Try expanding the date range or clearing the search.",
        "diary_count":          "{total} session(s) across {days} day(s)",
        "day_header_meta":      "{n} session(s) · {u}U {a}A",
        "diary_meta":           "{u} questions · {a} answers",
        "goto_conversation":    "Open in Conversation",

        # Workspaces tab
        "workspaces_title":     "Workspaces",
        "no_workspaces":        "No workspaces found.<br>Run the pipeline to update data.",
        "workspaces_count":     "{n} workspace(s) with recorded chat sessions.",
        "filter_by_folder":     "🔍 Filter by folder",
        "no_ws_filter":         "No workspace found for the applied filter.",
        "ws_first":             "First session",
        "ws_last":              "Last",
        "ws_sessions":          "{n} session(s)",
        "ws_questions":         "{u} questions",
        "ws_answers":           "{a} answers",
        "expand_sessions":      "View {n} session(s) from '{folder}'",

        # General states
        "no_data_error":        "File `sessions.jsonl` not found at:\n`{path}`\n\nRun the pipeline first:\n```\npython pipeline/02_normalize/normalize.py\n```",
        "no_sessions_main":     "No sessions available.<br>Run the pipeline to load data.",
        "select_session":       "Select a session from the sidebar.",
        "no_title":             "No title",
        "loading_data":         "Loading data...",

        # Weekdays
        "weekdays": {
            "Monday":    "Monday",
            "Tuesday":   "Tuesday",
            "Wednesday": "Wednesday",
            "Thursday":  "Thursday",
            "Friday":    "Friday",
            "Saturday":  "Saturday",
            "Sunday":    "Sunday",
        },
    },

    # -------------------------------------------------------------------------
    # Español (España)
    # -------------------------------------------------------------------------
    "es-ES": {
        # Sidebar
        "app_title":            "💬 Chat Viewer",
        "sessions_loaded":      "**{n}** sesiones cargadas",
        "theme_to_light":       "☀️ Tema claro",
        "theme_to_dark":        "🌙 Tema oscuro",
        "search_placeholder":   "🔍 Buscar por título o palabra clave",
        "source_filter_label":  "Fuente",
        "hide_empty":           "Ocultar sesiones vacías",
        "sessions_found":       "{n} sesión/sesiones encontrada(s)",
        "no_sessions_found":    "🔍 No se encontraron sesiones.<br>Prueba otros términos de búsqueda.",
        "session_select_label": "Sesión:",
        "run_pipeline_btn":     "🔄 Ejecutar pipeline",
        "pipeline_starting":    "Iniciando pipeline...",
        "pipeline_success":     "¡Pipeline completado! Recargando datos...",
        "pipeline_error":       "El pipeline terminó con error. Ver el registro arriba.",
        "pipeline_launch_error":"Error al iniciar el pipeline: {exc}",
        "language_label":       "🌐 Idioma",

        # Tabs
        "tab_conversation":     "💬 Conversación",
        "tab_diary":            "📅 Diario de Actividad",
        "tab_workspaces":       "🗂️ Espacios de trabajo",

        # Chat messages
        "role_user":            "Tú",
        "role_assistant":       "Asistente",
        "copy_text":            "📋 Copiar texto",
        "tool_args":            "Argumentos:",

        # Stat bar
        "stat_questions":       "Preguntas",
        "stat_answers":         "Respuestas",
        "stat_toolcalls":       "Tool calls",
        "stat_date":            "Fecha",
        "stat_sync":            "Últ. sinc.",

        # Export
        "save_to_workspace":    "📂 Guardar en workspace",
        "workspace_not_id":     "Workspace no identificado para esta sesión.",
        "save_file_btn":        "⬇️ Guardar archivo",
        "saved_success":        "✅ Guardado en: `{dest}`",
        "save_error":           "Error al guardar: {exc}",
        "export_json_btn":      "⬇️ Exportar JSON",
        "no_messages":          "No se encontraron mensajes para esta sesión.",
        "show_tool_calls":      "Mostrar tool calls",

        # Diario tab
        "diary_title":          "Diario de Actividad",
        "diary_caption":        "Sesiones agrupadas por día — ideal para documentar lo que se hizo.",
        "diary_search":         "🔍 Buscar por título o thread ID",
        "date_from":            "Desde:",
        "date_to":              "Hasta:",
        "no_diary_sessions":    "No se encontraron sesiones para los filtros aplicados.<br>Intenta ampliar el rango de fechas o borrar la búsqueda.",
        "diary_count":          "{total} sesión/sesiones en {days} día(s)",
        "day_header_meta":      "{n} sesión/sesiones · {u}U {a}A",
        "diary_meta":           "{u} preguntas · {a} respuestas",
        "goto_conversation":    "Abrir en Conversación",

        # Workspaces tab
        "workspaces_title":     "Espacios de trabajo",
        "no_workspaces":        "No se encontraron workspaces.<br>Ejecuta el pipeline para actualizar los datos.",
        "workspaces_count":     "{n} workspace(s) con sesiones de chat registradas.",
        "filter_by_folder":     "🔍 Filtrar por carpeta",
        "no_ws_filter":         "No se encontró ningún workspace para el filtro aplicado.",
        "ws_first":             "Primera sesión",
        "ws_last":              "Última",
        "ws_sessions":          "{n} sesión/sesiones",
        "ws_questions":         "{u} preguntas",
        "ws_answers":           "{a} respuestas",
        "expand_sessions":      "Ver {n} sesión/sesiones de '{folder}'",

        # General states
        "no_data_error":        "Archivo `sessions.jsonl` no encontrado en:\n`{path}`\n\nEjecuta el pipeline primero:\n```\npython pipeline/02_normalize/normalize.py\n```",
        "no_sessions_main":     "No hay sesiones disponibles.<br>Ejecuta el pipeline para cargar los datos.",
        "select_session":       "Selecciona una sesión en la barra lateral.",
        "no_title":             "Sin título",
        "loading_data":         "Cargando datos...",

        # Weekdays
        "weekdays": {
            "Monday":    "Lunes",
            "Tuesday":   "Martes",
            "Wednesday": "Miércoles",
            "Thursday":  "Jueves",
            "Friday":    "Viernes",
            "Saturday":  "Sábado",
            "Sunday":    "Domingo",
        },
    },
}

LANGUAGE_OPTIONS: dict[str, str] = {
    "pt-BR": "🇧🇷 Português (BR)",
    "en-US": "🇺🇸 English (US)",
    "es-ES": "🇪🇸 Español (ES)",
}


def get_translation(lang: str, key: str, **kwargs) -> str:
    """Retorna a string traduzida para `lang`. Faz fallback para pt-BR."""
    lang_dict = TRANSLATIONS.get(lang, TRANSLATIONS["pt-BR"])
    val = lang_dict.get(key, TRANSLATIONS["pt-BR"].get(key, key))
    if kwargs:
        try:
            return val.format(**kwargs)
        except (KeyError, AttributeError, IndexError):
            return val
    return val
