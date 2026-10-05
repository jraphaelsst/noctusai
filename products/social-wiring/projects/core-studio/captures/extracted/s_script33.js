
            (function configureEcho() {
                if (window.Echo && window.Echo.__advancedRoadmapConfigured) {
                    console.warn('[Echo] Já inicializado anteriormente, ignorando nova configuração.');
                    window.dispatchEvent(new CustomEvent('echo:ready'));
                    return;
                }

                const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
                const userId = document.querySelector('meta[name="user-id"]')?.getAttribute('content');
                const env = document.querySelector('meta[name="app-env"]')?.getAttribute('content') || 'local';

                const pusherKey = "75830eeb9f5ab6e769a8";
                const pusherCluster = "us2";
                const configuredHost = "api-us2.pusher.com";
                const configuredPort = "443";
                const forceTLS = true;

                const isCustomHost = configuredHost && !configuredHost.startsWith('api-');
                const wsHost = isCustomHost ? configuredHost : null;
                const wsPort = isCustomHost && configuredPort ? Number(configuredPort) : null;
                const wssPort = isCustomHost && configuredPort ? Number(configuredPort) : null;

                if (!pusherKey || pusherKey === 'null') {
                    console.error('[AdvancedRoadmapChat] Pusher key não configurado. Verifique broadcasting.php.');
                    return;
                }

                console.info('[AdvancedRoadmapChat] Bootstrap do Echo', {
                    pusherKey,
                    pusherCluster,
                    wsHost,
                    wsPort,
                    wssPort,
                    forceTLS,
                    env,
                    userId,
                });

                const echoOptions = {
                    broadcaster: 'pusher',
                    key: pusherKey,
                    cluster: pusherCluster,
                    forceTLS: forceTLS,
                    enabledTransports: ['ws', 'wss'],
                    disableStats: true,
                    encrypted: forceTLS,
                    authEndpoint: '/broadcasting/auth',
                    auth: {
                        headers: {
                            'X-CSRF-TOKEN': csrfToken,
                        },
                    },
                };

                if (wsHost) {
                    echoOptions.wsHost = wsHost;
                }
                if (wsPort) {
                    echoOptions.wsPort = wsPort;
                }
                if (wssPort) {
                    echoOptions.wssPort = wssPort;
                }

                window.Echo = new Echo(echoOptions);
                window.Echo.__advancedRoadmapConfigured = true;
                window.dispatchEvent(new CustomEvent('echo:ready'));

                const pusher = window.Echo.connector?.pusher;
                if (!pusher) {
                    console.error('[AdvancedRoadmapChat] Falha ao obter instância do Pusher via Echo.');
                    return;
                }

                pusher.connection.bind('connecting', () => console.debug('[Echo] Conectando...'));
                pusher.connection.bind('connected', () => console.info('[Echo] Conectado com sucesso.'));
                pusher.connection.bind('disconnected', () => console.warn('[Echo] Desconectado.'));
                pusher.connection.bind('unavailable', () => console.warn('[Echo] Servidor indisponível.'));
                pusher.connection.bind('failed', () => console.error('[Echo] Conexão falhou.'));
                pusher.connection.bind('error', (error) => console.error('[Echo] Erro na conexão Pusher', error));

                if (console && console.debug) {
                    pusher.bind_global((eventName, data) => {
                        console.debug('[Echo] Evento global recebido', eventName, data);
                    });
                }

                window.addEventListener('beforeunload', () => {
                    try {
                        window.Echo.disconnect();
                        console.debug('[Echo] Conexão encerrada (beforeunload).');
                    } catch (error) {
                        console.error('[Echo] Erro ao desconectar', error);
                    }
                });
            })();
        