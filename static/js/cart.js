// Auto-dismiss alerts after 4 seconds
document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('.alert.alert-dismissible').forEach(function (el) {
    setTimeout(function () {
      var bsAlert = bootstrap.Alert.getOrCreateInstance(el);
      bsAlert.close();
    }, 4000);
  });
});
