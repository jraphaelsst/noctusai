/* ===== SCRIPT #34 @673041 attrs= len=268 */

        $(document).ready(function() {
            $("#filterSelectV2").on("change", function() {
                var value = $(this).val();
                window.location.href = "https://corestudio.ai/dashboard/user?filter=" + value;
            })
        });
    
