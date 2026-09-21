from django.urls import path

from . import views
from .webhooks import pretix_webhook

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
        "sessions/<slug:slug>/",
        views.SessionDetailView.as_view(),
        name="session_detail",
    ),
    path(
        "sessions/<slug:slug>/edit/",
        views.SessionUpdateView.as_view(),
        name="session_edit",
    ),
    path(
        "sessions/<slug:slug>/presenters/add/",
        views.SessionAddPresenterView.as_view(),
        name="session_add_presenter",
    ),
    path(
        "sessions/<slug:slug>/presenters/<int:link_pk>/remove/",
        views.SessionRemovePresenterView.as_view(),
        name="session_remove_presenter",
    ),
    path(
        "sessions/<slug:slug>/presenters/<int:link_pk>/invite/",
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
        "presenters/<slug:slug>/",
        views.PresenterDetailView.as_view(),
        name="presenter_detail",
    ),
    path(
        "presenters/<slug:slug>/edit/",
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
        "me/sessions/<slug:slug>/edit/",
        views.SpeakerSessionUpdateView.as_view(),
        name="my_session_edit",
    ),
    path(
        "me/sessions/<slug:slug>/suggest/",
        views.SuggestCoPresenterView.as_view(),
        name="my_session_suggest",
    ),
    path("me/schedule/", views.SpeakerScheduleView.as_view(), name="my_schedule"),
    path("me/guide/", views.SpeakerGuideView.as_view(), name="my_guide"),
    path("me/guide/read/", views.SpeakerGuideReadView.as_view(), name="my_guide_read"),
    path(
        "settings/handbook/",
        views.HandbookListView.as_view(),
        name="handbook_list",
    ),
    path(
        "settings/handbook/<slug:key>/",
        views.HandbookEditorView.as_view(),
        name="handbook_editor",
    ),
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
        "presenters/<slug:slug>/items/add/",
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
        "presenters/<slug:slug>/invite/",
        views.PresenterInviteView.as_view(),
        name="presenter_invite",
    ),
    path(
        "invite/preview/",
        views.InvitationPreviewView.as_view(),
        name="invitation_preview",
    ),
    path(
        "presenters/<slug:slug>/pretix/lookup/",
        views.PresenterPretixLookupView.as_view(),
        name="presenter_pretix_lookup",
    ),
    path(
        "presenters/<slug:slug>/pretix/link/",
        views.PresenterPretixLinkView.as_view(),
        name="presenter_pretix_link",
    ),
    path(
        "webhooks/pretix/<slug:conference_slug>/",
        pretix_webhook,
        name="pretix_webhook",
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
