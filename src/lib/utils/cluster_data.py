from lib.common.errors import *


class Cluster:
    ## Construct Cluster object from dictionary, which should contain "host",
    #  "port", "admin_username" and "admin_pwd" keys.
    # @param data Dictionary with data.
    # @return Cluster object.
    def build_from_dict(data):
        try:
            return Cluster(data["host"], data["port"], data["admin_username"],
                           data["admin_pwd"])
        except KeyError as err:
            raise AutomationLibraryError("ARGS_ERROR",
                                         "cannot find key in cluster data",
                                         key=err.args[0])

    ## Constructor
    # @param self Pointer to object.
    # @param host Cluster host name.
    # @param port Cluster port.
    # @param admin_username Name of cluster's administrator user (account).
    # @param admin_username Password of cluster's administrator user (account).
    def __init__(self, host, port, admin_username, admin_pwd):
        # check, is port convertible to integer
        try:
           port = int(port)
        except ValueError:
            raise AutomationLibraryError(
                "ARGS_ERROR",
                "cluster port argument must be integer or string of digits",
                port_value = pgort
            )
        # fill values
        self.host = host
        self.port = port
        self.admin_username = admin_username
        self.admin_pwd = admin_pwd

    # cluster name is the same as host
    @property
    def name(self):
        return self.host

    @property
    def addr(self):
        return "{}:{}".format(self.host, self.port)

    def __str__(self):
        return "Cluster({}:{})".format(self.host, self.port)

    def __repr__(self):
        return "Cluster(host={},port={},admin_username={},admin_pwd={})".format(
            self.host, self.port, self.admin_username, self.admin_pwd
        )


class Infobase:
    ## Construct Cluster object from dictionary, which should contain "cluster",
    #  "name", "username" and "pwd" keys.
    def build_from_dict(data):
        try:
            return Infobase(Cluster.build_from_dict(data["cluster"]),
                            data["name"], data["username"], \
                            data["pwd"])
        except KeyError as err:
            raise AutomationLibraryError("ARGS_ERROR",
                                         "cannot find key in infobase data",
                                         key=err.args[0])

    ## Constructor.
    # @param self Pointer to object.
    # @param cluster Cluster object.
    # @param name Name of infobase.
    # @param username Name of user which allowed to perform certain actions on
    #  infobase.
    # @param pwd Password of this user.
    def __init__(self, cluster, name, username, pwd):
        # fill values
        self.cluster = cluster
        self.name = name
        self.username = username
        self.pwd = pwd

    def __str__(self):
        return "Infobase({}@{}:{})".format(self.name, self.cluster.host,
                                           self.cluster.port)

    def __repr__(self):
        return "Infobase(name={},cluster={},username={},password={})".format(
            self.name, repr(self.cluster), self.username, self.pwd
        )
