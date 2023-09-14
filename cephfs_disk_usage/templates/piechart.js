{% autoescape None %}

{% try %}
{% if not piechart %}{% end %}
{% except %}
<script src="https://cdn.plot.ly/plotly-2.25.2.min.js" charset="utf-8"></script>
{% set piechart = True %}
{% end %}

<script type="text/javascript">
{% set summary = data.child_summary() %}
var data = [{
  values: {{ json_encode([row.size for row in summary]) }},
  labels: {{ json_encode([row.name for row in summary]) }},
  type: 'pie',
  hole: .4,
  sort: false,
  direction: "clockwise",
  textinfo: "label+percent",
  textposition: "outside",
  textfont: {
    size: 12
  },
  automargin: true
}];

var layout = {
  margin: {"t": 0, "b": 0, "l": 0, "r": 0},
  showlegend: false
};

var config = {responsive: true}

Plotly.newPlot("piechart-{{ data.path }}", data, layout, config);
</script>