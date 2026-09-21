from django.urls import path, register_converter

from . import views
from .converters import UnicodeSlugConverter

register_converter(UnicodeSlugConverter, "uslug")

app_name = "speakers"

urlpatterns = [
    path("", views.SpeakerPortalIndexView.as_view(), name="index"),
    path(
        "invitations/<str:token>/",
        views.InvitationView.as_view(),
        name="invitation",
    ),
    path("sessions/", views.SessionListView.as_view(), name="session_list"),
    path("sessions/new/", views.SessionCreateView.as_view(), name="session_create"),
    path(
        "sessions/new-program-item/",
        views.ProgramItemCreateView.as_view(),
        name="program_item_create",
    ),
    path(
        "sessions/<uslug:slug>/",
        views.SessionDetailView.as_view(),
        name="session_detail",
    ),
    path(
        "sessions/<uslug:slug>/edit/",
        views.SessionUpdateView.as_view(),
        name="session_edit",
    ),
    path(
        "sessions/<uslug:slug>/presenters/add/",
        views.SessionAddPresenterView.as_view(),
        name="session_add_presenter",
    ),
    path(
        "sessions/<uslug:slug>/presenters/<int:link_pk>/remove/",
        views.SessionRemovePresenterView.as_view(),
        name="session_remove_presenter",
    ),
    path(
        "sessions/<uslug:slug>/presenters/<int:link_pk>/invite/",
        views.SessionInviteView.as_view(),
        name="session_invite",
    ),
    path("presenters/", views.PresenterListView.as_view(), name="presenter_list"),
    path(
        "presenters/new/",
        views.PresenterCreateView.as_view(),
        name="presenter_create",
    ),
    path(
        "presenters/<uslug:slug>/",
        views.PresenterDetailView.as_view(),
        name="presenter_detail",
    ),
    path(
        "presenters/<uslug:slug>/edit/",
        views.PresenterUpdateView.as_view(),
        name="presenter_edit",
    ),
    path("settings/types/", views.ProgramTypesView.as_view(), name="program_types"),
    path(
        "settings/types/new/",
        views.SessionTypeCreateView.as_view(),
        name="session_type_create",
    ),
    path(
        "settings/types/<int:pk>/",
        views.SessionTypeUpdateView.as_view(),
        name="session_type_edit",
    ),
    path(
        "settings/roles/new/",
        views.PresenterRoleCreateView.as_view(),
        name="presenter_role_create",
    ),
    path(
        "settings/roles/<int:pk>/",
        views.PresenterRoleUpdateView.as_view(),
        name="presenter_role_edit",
    ),
    path("me/", views.SpeakerDashboardView.as_view(), name="my_dashboard"),
    path("me/profile/", views.SpeakerProfileUpdateView.as_view(), name="my_profile"),
    path("me/sessions/", views.SpeakerSessionListView.as_view(), name="my_sessions"),
    path(
        "me/sessions/<uslug:slug>/edit/",
        views.SpeakerSessionUpdateView.as_view(),
        name="my_session_edit",
    ),
    path(
        "me/sessions/<uslug:slug>/suggest/",
        views.SuggestCoPresenterView.as_view(),
        name="my_session_suggest",
    ),
    path("me/schedule/", views.SpeakerScheduleView.as_view(), name="my_schedule"),
    path(
        "me/items/<int:pk>/toggle/",
        views.SpeakerItemToggleView.as_view(),
        name="my_item_toggle",
    ),
    path("checklists/", views.ChecklistBoardView.as_view(), name="checklist_board"),
    path(
        "checklists/export/",
        views.ChecklistBoardExportView.as_view(),
        name="checklist_board_export",
    ),
    path(
        "checklists/queue/", views.ChecklistQueueView.as_view(), name="checklist_queue"
    ),
    path("items/<int:pk>/status/", views.ItemStatusView.as_view(), name="item_status"),
    path("items/<int:pk>/assign/", views.ItemAssignView.as_view(), name="item_assign"),
    path(
        "presenters/<uslug:slug>/items/add/",
        views.PresenterAddItemView.as_view(),
        name="presenter_add_item",
    ),
    path(
        "settings/checklists/",
        views.ChecklistTemplateListView.as_view(),
        name="template_list",
    ),
    path(
        "settings/checklists/seed/",
        views.ChecklistTemplateSeedView.as_view(),
        name="template_seed",
    ),
    path(
        "settings/checklists/new/",
        views.ChecklistTemplateCreateView.as_view(),
        name="template_create",
    ),
    path(
        "settings/checklists/<int:pk>/",
        views.ChecklistTemplateDetailView.as_view(),
        name="template_detail",
    ),
    path(
        "settings/checklists/<int:pk>/edit/",
        views.ChecklistTemplateUpdateView.as_view(),
        name="template_edit",
    ),
    path(
        "settings/checklists/<int:pk>/items/add/",
        views.TemplateItemCreateView.as_view(),
        name="template_item_add",
    ),
    path(
        "settings/checklists/<int:pk>/items/<int:item_pk>/edit/",
        views.TemplateItemUpdateView.as_view(),
        name="template_item_edit",
    ),
    path(
        "settings/checklists/<int:pk>/items/<int:item_pk>/<slug:action>/",
        views.TemplateItemActionView.as_view(),
        name="template_item_action",
    ),
    path(
        "invitations/<int:pk>/resend/",
        views.InvitationResendView.as_view(),
        name="invitation_resend",
    ),
    path(
        "invitations/<int:pk>/cancel/",
        views.InvitationCancelView.as_view(),
        name="invitation_cancel",
    ),
]
