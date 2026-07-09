"""CDK stack: API Gateway + Lambda + S3 for opt-in tracker submit."""

from __future__ import annotations

import os
from pathlib import Path

from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
    aws_apigatewayv2 as apigwv2,
    aws_apigatewayv2_integrations as apigw_integrations,
    aws_budgets as budgets,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_logs as logs,
    aws_s3 as s3,
    aws_wafv2 as wafv2,
)
from constructs import Construct

LAMBDA_DIR = Path(__file__).resolve().parent / "lambda_handler"
COMMUNITY_PREFIX = "community"


class TrackerSubmitStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        budget_alert_email: str = "",
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        bucket = s3.Bucket(
            self,
            "TrackerDataBucket",
            bucket_name=f"cngx-tracker-{self.account}-{self.region}",
            versioned=True,
            block_public_access=s3.BlockPublicAccess(
                block_public_acls=True,
                ignore_public_acls=True,
                block_public_policy=False,
                restrict_public_buckets=False,
            ),
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.RETAIN,
            auto_delete_objects=False,
            cors=[
                s3.CorsRule(
                    allowed_methods=[s3.HttpMethods.GET, s3.HttpMethods.HEAD],
                    allowed_origins=["*"],
                    allowed_headers=["*"],
                    max_age=300,
                )
            ],
        )

        bucket.add_to_resource_policy(
            iam.PolicyStatement(
                sid="PublicReadCommunityObjectsOnly",
                effect=iam.Effect.ALLOW,
                principals=[iam.AnyPrincipal()],
                actions=["s3:GetObject"],
                resources=[bucket.arn_for_objects(f"{COMMUNITY_PREFIX}/*")],
            )
        )

        bucket.add_to_resource_policy(
            iam.PolicyStatement(
                sid="DenyPublicListBucket",
                effect=iam.Effect.DENY,
                principals=[iam.AnyPrincipal()],
                actions=["s3:ListBucket"],
                resources=[bucket.bucket_arn],
            )
        )

        log_group = logs.LogGroup(
            self,
            "SubmitFunctionLogs",
            retention=logs.RetentionDays.TWO_WEEKS,
        )

        fn = lambda_.Function(
            self,
            "SubmitFunction",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="handler.handler",
            code=lambda_.Code.from_asset(str(LAMBDA_DIR)),
            timeout=Duration.seconds(15),
            memory_size=256,
            environment={
                "BUCKET_NAME": bucket.bucket_name,
                "OBJECT_PREFIX": COMMUNITY_PREFIX,
            },
            log_group=log_group,
        )

        fn.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["s3:GetObject", "s3:PutObject"],
                resources=[bucket.arn_for_objects(f"{COMMUNITY_PREFIX}/*")],
            )
        )

        http_api = apigwv2.HttpApi(
            self,
            "SubmitHttpApi",
            api_name="cngx-tracker-submit",
            description="Opt-in drift metric submissions for the cngx tracker",
            cors_preflight=apigwv2.CorsPreflightOptions(
                allow_methods=[apigwv2.CorsHttpMethod.POST, apigwv2.CorsHttpMethod.OPTIONS],
                allow_origins=["*"],
                allow_headers=["content-type"],
                max_age=Duration.hours(1),
            ),
        )

        integration = apigw_integrations.HttpLambdaIntegration(
            "SubmitIntegration",
            fn,
        )

        http_api.add_routes(
            path="/submit",
            methods=[apigwv2.HttpMethod.POST],
            integration=integration,
        )

        stage = http_api.default_stage
        if stage is not None:
            cfn_stage: apigwv2.CfnStage = stage.node.default_child
            cfn_stage.default_route_settings = apigwv2.CfnStage.RouteSettingsProperty(
                throttling_burst_limit=10,
                throttling_rate_limit=5,
            )

        # HTTP APIs do not support regional WAF association; use CloudFront + WAF (CLOUDFRONT scope).
        web_acl = wafv2.CfnWebACL(
            self,
            "SubmitWebAcl",
            default_action=wafv2.CfnWebACL.DefaultActionProperty(allow={}),
            scope="CLOUDFRONT",
            visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                cloud_watch_metrics_enabled=True,
                metric_name="cngxTrackerSubmitAcl",
                sampled_requests_enabled=True,
            ),
            rules=[
                wafv2.CfnWebACL.RuleProperty(
                    name="RateLimitPerIp",
                    priority=1,
                    action=wafv2.CfnWebACL.RuleActionProperty(block={}),
                    statement=wafv2.CfnWebACL.StatementProperty(
                        rate_based_statement=wafv2.CfnWebACL.RateBasedStatementProperty(
                            limit=100,
                            aggregate_key_type="IP",
                        )
                    ),
                    visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                        cloud_watch_metrics_enabled=True,
                        metric_name="cngxTrackerSubmitRateLimit",
                        sampled_requests_enabled=True,
                    ),
                )
            ],
        )

        api_hostname = f"{http_api.api_id}.execute-api.{self.region}.amazonaws.com"
        distribution = cloudfront.Distribution(
            self,
            "SubmitDistribution",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.HttpOrigin(
                    api_hostname,
                    protocol_policy=cloudfront.OriginProtocolPolicy.HTTPS_ONLY,
                ),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.HTTPS_ONLY,
                allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
            ),
            web_acl_id=web_acl.attr_arn,
            comment="cngx tracker submit edge",
        )

        email = budget_alert_email or os.environ.get("AWS_BILLING_ALERT_EMAIL", "")
        if email:
            budgets.CfnBudget(
                self,
                "TrackerBudgetAlert",
                budget=budgets.CfnBudget.BudgetDataProperty(
                    budget_name="cngx-tracker-monthly",
                    budget_type="COST",
                    time_unit="MONTHLY",
                    budget_limit=budgets.CfnBudget.SpendProperty(amount=5, unit="USD"),
                ),
                notifications_with_subscribers=[
                    budgets.CfnBudget.NotificationWithSubscribersProperty(
                        notification=budgets.CfnBudget.NotificationProperty(
                            notification_type="ACTUAL",
                            comparison_operator="GREATER_THAN",
                            threshold=80,
                            threshold_type="PERCENTAGE",
                        ),
                        subscribers=[
                            budgets.CfnBudget.SubscriberProperty(
                                subscription_type="EMAIL",
                                address=email,
                            )
                        ],
                    ),
                    budgets.CfnBudget.NotificationWithSubscribersProperty(
                        notification=budgets.CfnBudget.NotificationProperty(
                            notification_type="FORECASTED",
                            comparison_operator="GREATER_THAN",
                            threshold=100,
                            threshold_type="PERCENTAGE",
                        ),
                        subscribers=[
                            budgets.CfnBudget.SubscriberProperty(
                                subscription_type="EMAIL",
                                address=email,
                            )
                        ],
                    ),
                ],
            )

        submit_url = f"https://{distribution.distribution_domain_name}/submit"
        data_url = f"https://{bucket.bucket_name}.s3.{self.region}.amazonaws.com/{COMMUNITY_PREFIX}/index.json"

        CfnOutput(self, "SubmitApiUrl", value=submit_url)
        CfnOutput(self, "SubmitApiDirectUrl", value=f"{http_api.api_endpoint}/submit")
        CfnOutput(self, "TrackerIndexUrl", value=data_url)
        CfnOutput(self, "TrackerBucketName", value=bucket.bucket_name)
