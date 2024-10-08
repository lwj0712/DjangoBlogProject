from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseRedirect, HttpResponseForbidden, JsonResponse
from django.db.models import Count
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse, reverse_lazy
from .forms import PostForm, CommentForm, CommentReplyForm
from .models import Post, Comment, Like, Category
from django.views import View
from django.views.generic import (
    TemplateView,
    CreateView,
    ListView,
    DetailView,
    UpdateView,
    DeleteView,
)


class MainPageView(TemplateView):
    template_name = "main_page.html"


class PostListView(ListView):
    model = Post
    template_name = "blog/post_list.html"
    context_object_name = "posts"
    ordering = ["-created_at"]
    paginate_by = 5

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = queryset.annotate(like_count=Count("likes"))  # 좋아요 수를 미리 계산
        query = self.request.GET.get("query")
        search_type = self.request.GET.get("search_type")
        category_slug = self.request.GET.get("category")

        if query:
            if search_type == "title":
                queryset = queryset.filter(title__icontains=query)
            elif search_type == "content":
                queryset = queryset.filter(content__icontains=query)
            elif search_type == "author":
                queryset = queryset.filter(author__username__icontains=query)

        if category_slug:
            queryset = queryset.filter(category__slug=category_slug)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        most_liked_posts = Post.objects.annotate(like_count=Count("likes")).order_by(
            "-like_count"
        )[:5]
        categories = Category.objects.all()

        context.update(
            {
                "most_liked_posts": most_liked_posts,
                "is_authenticated": self.request.user.is_authenticated,
                "categories": categories,
                "selected_category": self.request.GET.get("category"),
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        post_pk = kwargs.get("pk")
        post = get_object_or_404(Post, pk=post_pk)

        if "comment_form" in request.POST:
            return self.handle_comment(request, post)
        elif "reply_form" in request.POST:
            return self.handle_comment(
                request, post, parent_comment_id=request.POST.get("parent_comment_id")
            )

        return self.get(request, *args, **kwargs)

    def handle_comment(self, request, post, parent_comment_id=None):
        if parent_comment_id:
            parent_comment = get_object_or_404(Comment, pk=parent_comment_id)
            reply_form = CommentReplyForm(
                request.POST, parent_comment_id=parent_comment.pk
            )
            if reply_form.is_valid():
                reply = reply_form.save(commit=False)
                reply.post = post
                reply.author = request.user
                reply.parent = parent_comment
                reply.save()
                return redirect("blog:post_detail", pk=post.pk)
        else:
            comment_form = CommentForm(request.POST)
            if comment_form.is_valid():
                comment = comment_form.save(commit=False)
                comment.post = post
                comment.author = request.user
                comment.save()
                return redirect("blog:post_detail", pk=post.pk)

        return self.get(request)


class PostDetailView(DetailView):
    model = Post
    template_name = "blog/post_detail.html"
    context_object_name = "post"
    pk_url_kwarg = "pk"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        post = self.get_object()
        post.view_count += 1
        post.save()

        # 댓글, 대댓글 기능
        post_pk = self.kwargs.get("pk")
        context["comments"] = Comment.objects.filter(post_id=post_pk, parent=None)
        context["comment_form"] = CommentForm()
        context["reply_form"] = CommentReplyForm()

        return context


class PostCreateView(LoginRequiredMixin, CreateView):
    model = Post
    form_class = PostForm
    template_name = "blog/post_form.html"
    success_url = reverse_lazy("blog:post_list")

    def form_valid(self, form):
        form.instance.author = self.request.user
        return super().form_valid(form)


class PostUpdateView(UserPassesTestMixin, UpdateView):
    model = Post
    form_class = PostForm
    template_name = "blog/post_form.html"
    success_url = reverse_lazy("blog:post_list")

    def get_object(self, queryset=None):
        return get_object_or_404(Post, pk=self.kwargs["pk"])

    def test_func(self):
        post = self.get_object()
        return self.request.user == post.author

    # test_func이 False를 반환할 때 호출
    def handle_no_permission(self):
        return HttpResponseForbidden("권한이 없습니다.")


class PostDeleteView(UserPassesTestMixin, DeleteView):
    model = Post
    success_url = reverse_lazy("blog:post_list")
    template_name = "blog/post_confirm_delete.html"

    def get_object(self, queryset=None):
        return get_object_or_404(Post, pk=self.kwargs["pk"])

    # 사용자가 해당 게시글의 작성자인지 확인
    def test_func(self):
        post = self.get_object()
        return self.request.user == post.author

    # test_func이 False를 반환 시 호출
    def handle_no_permission(self):
        return HttpResponseForbidden("권한이 없습니다.")


class PostSearchView(ListView):
    model = Post
    template_name = "blog/post_list.html"
    context_object_name = "posts"

    def get_queryset(self):
        tag = self.kwargs["tag"]
        return Post.objects.filter(category__name__icontains=tag).order_by(
            "-created_at"
        )


class CommentCreateView(LoginRequiredMixin, CreateView):
    model = Comment
    form_class = CommentForm
    template_name = "blog/post_detail.html"

    def form_valid(self, form):
        post_pk = self.kwargs["post_pk"]
        post = get_object_or_404(Post, pk=post_pk)
        form.instance.post = post
        form.instance.author = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy("blog:post_detail", kwargs={"pk": self.kwargs["post_pk"]})


class CommentReplyView(LoginRequiredMixin, CreateView):
    model = Comment
    form_class = CommentForm
    template_name = "blog/post_detail.html"

    def form_valid(self, form):
        post_pk = self.kwargs["post_pk"]
        comment_pk = self.kwargs["comment_pk"]
        post = get_object_or_404(Post, pk=post_pk)
        parent_comment = get_object_or_404(Comment, pk=comment_pk)
        form.instance.post = post
        form.instance.author = self.request.user
        form.instance.parent = parent_comment
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy("blog:post_detail", kwargs={"pk": self.kwargs["post_pk"]})


class CommentDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = Comment

    def get_object(self, queryset=None):
        comment_pk = self.kwargs.get("comment_pk")
        return get_object_or_404(Comment, pk=comment_pk)

    def get_success_url(self):
        return self.request.META.get("HTTP_REFERER", reverse_lazy("blog:post_list"))

    def delete(self, request, *args, **kwargs):
        comment = self.get_object()
        if comment.author == request.user:
            if comment.is_deleted:
                return HttpResponseRedirect(self.get_success_url())
            if comment.replies.exists():
                comment.is_deleted = True
                comment.content = "(삭제된 메시지입니다.)"
                comment.save()
            else:
                comment.delete()

        return HttpResponseRedirect(self.get_success_url())

    def test_func(self):
        comment = self.get_object()
        return self.request.user == comment.author

    def handle_no_permission(self):
        return HttpResponseForbidden("권한이 없습니다.")


class LikeToggleView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        pk = kwargs.get("pk")
        post = get_object_or_404(Post, pk=pk)
        like, created = Like.objects.get_or_create(user=request.user, post=post)

        if not created:
            like.delete()

        # 좋아요 JSON으로 반환
        return JsonResponse({"liked": created, "like_count": post.likes.count()})


def custom_page_not_found_view(request, exception):
    return render(request, "404.html", status=404)
