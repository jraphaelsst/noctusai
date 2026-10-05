$('form#save_profile').submit(function (e){
    "use strict";

    e.preventDefault();

    var $form = $(this);
    var bio = ($('textarea[name="bio"]').val() || '').trim();
    var niches = $('select#niche-select').val() || [];
    var professions = $('select#profession-select').val() || [];
    if (!Array.isArray(niches)) niches = niches ? [niches] : [];
    if (!Array.isArray(professions)) professions = professions ? [professions] : [];
    var hasBio = bio.length > 0;
    var hasNiches = niches.length > 0;
    var hasProfessions = professions.length > 0;

    var showWarningModal = (hasNiches && hasProfessions && !hasBio) || (hasBio && (!hasNiches || !hasProfessions));

    function doSubmit() {
        $('#button_save_profile').prop('disabled', true);
        $('#button_save_profile').text('Aguarde atualizando...');
        var formData = new FormData($form[0]);
        $.ajax({
            type: "post",
            url: "/dashboard/user/profile/save",
            data: formData,
            contentType: false,
            processData: false,
            success: function(data){
                toastr[data.type](data.message);
                if(data.refresh){
                    setTimeout(function(){ window.location.reload(); }, 1000);
                }
            },
            error: function(data){
                if (data.status === 422) {
                    var errors = data.responseJSON.errors;
                    $.each(errors, function(index, value) { toastr.error(value); });
                } else {
                    toastr.error('Ocorreu um erro ao atualizar o perfil.');
                }
                $('#button_save_profile').prop('disabled', false);
                $('#button_save_profile').html('Atualizar');
            }
        });
    }

    if (showWarningModal && $('#profileIncompleteModal').length) {
        var modalEl = document.getElementById('profileIncompleteModal');
        var modal = bootstrap.Modal.getOrCreateInstance(modalEl);
        $('#profileIncompleteModalConfirm').off('click.profileSubmit').on('click.profileSubmit', function() {
            modal.hide();
            doSubmit();
        });
        modal.show();
        return false;
    }

    doSubmit();
    return false;
});
