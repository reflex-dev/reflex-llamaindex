import reflex as rx

config = rx.Config(
    app_name="docs_chat",
    plugins=[
        rx.plugins.SitemapPlugin(),
        rx.plugins.TailwindV4Plugin(),
        rx.plugins.RadixThemesPlugin(
            theme=rx.theme(appearance="light", accent_color="violet", radius="large")
        ),
    ],
)
