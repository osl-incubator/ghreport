# {{report_title}} <a name="{{report_title.lower().replace(" ", "-")}}"></a>

|                   |                 |
|:------------------|:----------------|
|**Repositories**   |{{orgs_repos}}   |
|**Authors**        |{{authors}}      |
|**Start Date**     |{{start_date}}   |
|**End Date**       |{{end_date}}     |


**Table of Contents**

- [{{report_title}}](#{{report_title.lower().replace(" ", "-")}})
{% for project in projects %}
 {% if project.issue_results != "None" or project.pr_results != "None" %}
  - [{{project.name}}](#{{project.name.lower().replace(" ", "-")}})
 {% endif %}
{% endfor %}


<!-- PROJECTS -->

{% for project in projects %}

{% if project.issue_results != "None" or project.pr_results != "None" %}

## {{project.name}}

{% if project.pr_results != "None" %}
### Pull Requests ({{project.name}})

{{project.pr_results}}
{% endif %}

{% if project.issue_results != "None" %}
### Issues ({{project.name}})

{{project.issue_results}}
{% endif %}

{% endif %}

{% endfor %}
