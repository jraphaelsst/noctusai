
    let chatRecording = {
        isRecording: false,
        timer: null,
        seconds: 0,
        mediaRecorder: null,
        audioChunks: [],
        audioBlob: null,
        audioContext: null,
        analyser: null,
        dataArray: null
    };

    // Insere ícones SVG
    $(".icon-microphone-chat").html(`<svg  xmlns="http://www.w3.org/2000/svg"  width="24"  height="24"  viewBox="0 0 24 24"  fill="currentColor"  class="icon icon-tabler icons-tabler-filled icon-tabler-microphone"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M19 9a1 1 0 0 1 1 1a8 8 0 0 1 -6.999 7.938l-.001 2.062h3a1 1 0 0 1 0 2h-8a1 1 0 0 1 0 -2h3v-2.062a8 8 0 0 1 -7 -7.938a1 1 0 1 1 2 0a6 6 0 0 0 12 0a1 1 0 0 1 1 -1m-7 -8a4 4 0 0 1 4 4v5a4 4 0 1 1 -8 0v-5a4 4 0 0 1 4 -4" /></svg>`);
    $(".icon-pause-chat").html(`<svg  xmlns="http://www.w3.org/2000/svg"  width="24"  height="24"  viewBox="0 0 24 24"  fill="currentColor"  class="icon icon-tabler icons-tabler-filled icon-tabler-player-pause"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M9 4h-2a2 2 0 0 0 -2 2v12a2 2 0 0 0 2 2h2a2 2 0 0 0 2 -2v-12a2 2 0 0 0 -2 -2z" /><path d="M17 4h-2a2 2 0 0 0 -2 2v12a2 2 0 0 0 2 2h2a2 2 0 0 0 2 -2v-12a2 2 0 0 0 -2 -2z" /></svg>`);
    $(".icon-trash-chat").html(`<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"  viewBox="0 0 24 24"  fill="none"  stroke="currentColor"  stroke-width="2"  stroke-linecap="round"  stroke-linejoin="round"  class="icon icon-tabler icons-tabler-outline icon-tabler-trash"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M4 7l16 0" /><path d="M10 11l0 6" /><path d="M14 11l0 6" /><path d="M5 7l1 12a2 2 0 0 0 2 2h8a2 2 0 0 0 2 -2l1 -12" /><path d="M9 7v-3a1 1 0 0 1 1 -1h4a1 1 0 0 1 1 1v3" /></svg>`);

    // Configura canvas
    function setupChatCanvas(canvas) {
        const scale = window.devicePixelRatio || 1;
        canvas.width = canvas.offsetWidth * scale;
        canvas.height = canvas.offsetHeight * scale;
        canvas.getContext("2d").scale(scale, scale);
    }

    // Clique no botão de gravação
    $("#record-button-chat").click(async () => {
        const canvas = document.getElementById("waveform-chat");
        const micIcon = $("#record-button-chat .mic-icon");
        const micPause = $("#record-button-chat .mic-pause");
        const timerEl = $("#record-timer-chat");
        const divAudio = $(".div-audio-chat");
        const divControls = $(".div-controls-chat");
        const player = $("#audio-player-chat");

        setupChatCanvas(canvas);

        if (!chatRecording.isRecording) {
            try {
                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                chatRecording.audioContext = new AudioContext();
                chatRecording.analyser = chatRecording.audioContext.createAnalyser();
                chatRecording.analyser.fftSize = 256;
                chatRecording.dataArray = new Uint8Array(chatRecording.analyser.frequencyBinCount);
                const source = chatRecording.audioContext.createMediaStreamSource(stream);
                source.connect(chatRecording.analyser);

                chatRecording.mediaRecorder = new MediaRecorder(stream, {
                    mimeType: 'audio/webm'
                });
                chatRecording.audioChunks = [];
                chatRecording.mediaRecorder.ondataavailable = e => chatRecording.audioChunks.push(e.data);
                chatRecording.mediaRecorder.start();

                chatRecording.seconds = 0;
                timerEl.text("00:00");
                chatRecording.timer = setInterval(() => {
                    chatRecording.seconds++;
                    timerEl.text(new Date(chatRecording.seconds * 1000).toISOString().substr(14, 5));
                }, 1000);

                micIcon.addClass("hidden");
                micPause.removeClass("hidden");
                chatRecording.isRecording = true;

                // animação canvas
                const ctx = canvas.getContext("2d");
                function draw() {
                    if (!chatRecording.isRecording) return;
                    chatRecording.analyser.getByteFrequencyData(chatRecording.dataArray);
                    ctx.clearRect(0, 0, canvas.width, canvas.height);
                    let x = 0;
                    const barCount = 120;
                    const barWidth = Math.floor(canvas.width / barCount) - 2;
                    for (let i = 0; i < barCount; i++) {
                        const index = Math.floor((i / barCount) * chatRecording.dataArray.length);
                        const height = (chatRecording.dataArray[index] / 255) * canvas.height * 0.8;
                        ctx.fillStyle = "#00BFFF";
                        ctx.fillRect(x, (canvas.height - height) / 2, barWidth, height);
                        x += barWidth + 2;
                    }
                    requestAnimationFrame(draw);
                }
                draw();
            } catch (error) {
                alert("Erro ao acessar o microfone.");
                console.error(error);
            }
        } else {
            // Parar
            chatRecording.isRecording = false;
            micIcon.removeClass("hidden");
            micPause.addClass("hidden");
            clearInterval(chatRecording.timer);
            chatRecording.mediaRecorder.stop();

            chatRecording.mediaRecorder.onstop = () => {
                console.log('MediaRecorder parou');
                console.log('Audio chunks:', chatRecording.audioChunks.length);

                chatRecording.audioBlob = new Blob(chatRecording.audioChunks, { type: 'audio/webm' });
                console.log('Audio blob criado:', !!chatRecording.audioBlob);

                const url = URL.createObjectURL(chatRecording.audioBlob);
                console.log('URL criada:', url);

                player.attr("src", url);
                divAudio.addClass("hidden");
                divControls.removeClass("hidden");

                player[0].onloadedmetadata = () => {
                    if (player[0].duration === Infinity) {
                        player[0].currentTime = 1e101;
                        player[0].ontimeupdate = () => {
                            player[0].ontimeupdate = null;
                            player[0].currentTime = 0; // volta ao início
                        };
                    }
                };


                // Atualizar o estado do Alpine
                const alpineComponent = document.querySelector('[x-data="aiChat"]').__x;
                if (alpineComponent) {
                    // Forçar atualização do estado
                    alpineComponent.$data.audioUrl = url;
                    alpineComponent.$data.audioBlob = chatRecording.audioBlob;
                    alpineComponent.$data.isLoading = false;

                    // Debug
                    console.log('Audio Blob definido no Alpine:', !!alpineComponent.$data.audioBlob);
                    console.log('Audio URL definido no Alpine:', !!alpineComponent.$data.audioUrl);
                }

                // Garantir que chatRecording está acessível globalmente
                window.chatRecording = chatRecording;
                console.log('chatRecording definido globalmente:', !!window.chatRecording);
                console.log('chatRecording.audioBlob global:', !!window.chatRecording.audioBlob);
            };
        }
    });

    // Botão de apagar - agora controlado pelo Alpine.js
    // $("#delete-button-chat").click(() => {
    //     // Usar o Alpine.js para resetar os controles
    //     const alpineComponent = document.querySelector('[x-data="aiChat"]').__x;
    //     if (alpineComponent) {
    //         alpineComponent.switchToText();
    //     }
    //
    //     // Resetar elementos específicos do áudio
    //     $(".div-controls-chat").addClass("hidden");
    //     $(".div-audio-chat").removeClass("hidden");
    //     $("#record-timer-chat").text("00:00");
    //     $("#audio-player-chat").attr("src", "");

    //     // Resetar variáveis do chatRecording
    //     chatRecording = {
    //         isRecording: false,
    //         timer: null,
    //         seconds: 0,
    //         mediaRecorder: null,
    //         audioChunks: [],
    //         audioBlob: null,
    //         audioContext: null,
    //         analyser: null,
    //         dataArray: null
    //     };
    // });

    // Adicionar evento de clique no botão de enviar áudio
    $('.sendAudio').on('click', function() {
        const alpineComponent = document.querySelector('[x-data="aiChat"]').__x;
        if (alpineComponent && chatRecording.audioBlob) {
            // Garantir que o audioBlob está definido antes de chamar sendMessage
            alpineComponent.$data.audioBlob = chatRecording.audioBlob;
            alpineComponent.$data.audioUrl = URL.createObjectURL(chatRecording.audioBlob);
            alpineComponent.sendMessage();
        }
    });

