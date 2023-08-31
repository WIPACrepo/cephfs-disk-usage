{% autoescape None %}

<script type="text/javascript">
{% set funcname = 'draw'+data.path.replace('.','').replace('/','').replace('-','') %}
{% set datatable = json_encode([['Name', 'Size']]+[[row.name, row.size] for row in data.children]) %}
google.charts.load('current', {'packages':['corechart']});
google.charts.setOnLoadCallback({{ funcname }});

function {{ funcname }}() {

  var data = google.visualization.arrayToDataTable({{ datatable }});

  var options = {
 //   title: 'My Daily Activities'
  };

  var chart = new google.visualization.PieChart(document.getElementById("piechart-{{ data.path }}"));

  chart.draw(data, options);
}
</script>