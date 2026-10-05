
    let mediaRecorder = null;
    let audioChunks = [];
    let isRecording = false;

    // Removido os eventos jQuery que controlavam a visibilidade dos botões
    // Agora isso é controlado pelo Alpine.js de forma reativa

    // Evento de clique no microfone agora é controlado pelo Alpine
    // $('.microphone-chat').click(function(){
    //     $('.audio-area-chat').removeClass('hidden');
    //     $('.input-message').addClass('hidden');
    //     $('.sendText').addClass('hidden');
    //     $('.microphone-chat').addClass('hidden');
    //     $("#record-button-chat").click();
    // });

