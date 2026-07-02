# skills/whatsapp_assistant/

Skill empaquetable para integrar `wpp_analytics` en agentes de IA (Gemini, OpenAI, MiniMax, etc.).

## Estructura objetivo

```
whatsapp_assistant/
├── SKILL.md                  ← manifiesto + recetas de invocación
└── scripts/
    ├── analizar_contexto.py  ← copia o symlink al script principal
    └── buscar_datos.py       ← copia o symlink al buscador
```

## Pendiente (Fase 5 del roadmap)

- [ ] Definir `SKILL.md` con instrucciones para la IA.
- [ ] Copiar/symlinkear los scripts desde `../../scripts/`.
- [ ] Validar invocación desde un agente real.